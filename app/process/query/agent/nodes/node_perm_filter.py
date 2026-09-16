# -*- coding: utf-8 -*-
"""
节点: 四维数据权限过滤 (node_perm_filter) —— M1-05 核心节点。

位置：node_rerank 之后、node_answer_output 之前（召回与精排完成后、提示词组装前）。

职责（需求 2.9.4）：
1. 对精排后的候选切片，按其归属知识单元做四维权限判定（全局/部门/角色/个人 OR，默认拒绝）
2. 仅放行切片保留进 reranked_docs（提示词组装只含有权内容）
3. 拦截切片标识写入 denied_knowledge_ids（审计与前端受限提示用，绝不进入提示词）
4. 全部被拦截时短路：直接写入受限提示 answer，跳过 LLM 生成与语义缓存写入
"""
import sys

from app.infra.persistence.knowledge_repository import knowledge_id_of
from app.infra.persistence.permission_repository import permission_repository
from app.infra.security.perm_engine import has_access
from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task

PERMISSION_DENIED_ANSWER = (
    "检测到相关制度文档，但您当前所属部门/角色无权查阅该内容。\n\n"
    "如因工作需要访问，请联系知识管理员为您的部门或角色申请对应知识单元的权限。"
)


@node_log("node_perm_filter")
def node_perm_filter(state):
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))

    docs = state.get("reranked_docs") or []
    if not docs:
        add_done_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))
        return state

    user_ctx = {
        "user_id": state.get("user_id", ""),
        "department_id": state.get("department_id", ""),
        "role_ids": state.get("roles", []),
    }

    # file_title 与知识单元一一对应（台账登记与向量清理同键），kid 稳定派生
    kid_by_file_title = {knowledge_id_of(d.get("file_title", "")): d.get("file_title", "") for d in docs}
    perm_docs = permission_repository.list_by_knowledge_ids(list(kid_by_file_title.keys()))
    perms_by_kid = {d["knowledge_id"]: d.get("perms") for d in perm_docs}

    allowed_docs: list[dict] = []
    denied_docs: list[dict] = []
    for d in docs:
        kid = knowledge_id_of(d.get("file_title", ""))
        # 无权限记录的知识单元 → 无任何公开权限，默认拒绝
        if has_access(user_ctx, perms_by_kid.get(kid)):
            allowed_docs.append(d)
        else:
            denied_docs.append(d)

    state["reranked_docs"] = allowed_docs
    state["allowed_knowledge_ids"] = sorted({knowledge_id_of(d.get("file_title", "")) for d in allowed_docs})
    state["denied_knowledge_ids"] = sorted({knowledge_id_of(d.get("file_title", "")) for d in denied_docs})

    if denied_docs and not allowed_docs:
        # 全部命中内容均无权限：短路返回受限提示，不调用 LLM、不写缓存
        state["answer"] = PERMISSION_DENIED_ANSWER
        state["skip_cache"] = True

    add_done_task(state["session_id"], sys._getframe().co_name if False else sys._getframe().f_code.co_name, state.get("is_stream"))
    return state
