# -*- coding: utf-8 -*-
# @Time : 2026/06/12
# @Author : lzm

"""
 @description 历史上下文压缩服务，阈值触发 + 增量摘要

 @dependency history_repository, llm_provider

 @output history_context 文本供后续节点消费
"""

import json
from datetime import datetime

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser

from app.infra.llm.providers import llm_provider
from app.infra.persistence.history_repository import history_repository
from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import (
    HISTORY_CHUNK_SIZE,
    HISTORY_COMPRESS_ENABLED,
    HISTORY_RECENT_LIMIT,
    HISTORY_TOKEN_THRESHOLD,
)
from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import logger, step_log


def filter_valid_messages(messages: list[dict]) -> list[dict]:
    """
    过滤有效历史（item_names非空）
    :param messages: 原始消息列表
    :return: 有效消息列表
    """
    return [
        item for item in messages
        if item.get("item_names") and len(item.get("item_names", [])) > 0
    ]


def estimate_tokens(messages: list[dict]) -> int:
    """
    估算消息token数（字符数/2近似）
    :param messages: 消息列表
    :return: 估算token数
    """
    total = 0
    for msg in messages:
        # 用户消息取 rewritten_query，助手消息取 text
        text = msg.get("rewritten_query") if msg.get("role") == "user" else msg.get("text", "")
        total += len(str(text))
    return total // 2


def format_messages_text(messages: list[dict]) -> str:
    """
    将消息列表格式化为历史上下文文本
    :param messages: 消息列表（时间正序）
    :return: 格式化文本
    """
    if not messages:
        return "没有对话记录!"
    lines = []
    for index, item in enumerate(messages, start=1):
        content = item["rewritten_query"] if item["role"] == "user" else item["text"]
        lines.append(
            f"序号:{index},类型:{'提问' if item['role'] == 'user' else '回答'},"
            f"内容:{content},关联主体:{','.join(item['item_names'])}"
        )
    return "\n".join(lines)


def count_messages_after(messages: list[dict], last_msg_id: str | None) -> int:
    """
    统计自上次压缩边界之后的新消息数
    :param messages: 全部有效消息（时间正序）
    :param last_msg_id: 上次压缩边界消息ID（last_compressed_msg_id）
    :return: 新消息数量
    """
    # 首次压缩：尚无边界，视为全部消息待统计
    if not last_msg_id:
        return len(messages)
    found = False
    count = 0
    for msg in messages:
        if found:
            count += 1
        if str(msg.get("_id")) == str(last_msg_id):
            found = True
    # 边界消息找不到时兜底返回全量（防止脏数据导致永远不压缩）
    return count if found else len(messages)


def get_messages_after(messages: list[dict], last_msg_id: str | None) -> list[dict]:
    """
    获取待送入LLM压缩的消息片段
    :param messages: 全部有效消息（时间正序）
    :param last_msg_id: 上次压缩边界消息ID
    :return: 待压缩消息列表
    """
    # 首次压缩：取「近N条」以外的更早消息（即 messages[:-N]）
    if not last_msg_id:
        older_count = max(0, len(messages) - HISTORY_RECENT_LIMIT)
        return messages[:older_count]
    # 增量压缩：取边界消息之后的所有消息
    result = []
    found = False
    for msg in messages:
        if found:
            result.append(msg)
        if str(msg.get("_id")) == str(last_msg_id):
            found = True
    return result


@step_log("should_compress")
def should_compress(valid_messages: list[dict], session_context: dict | None) -> bool:
    """
    判断本次查询是否需要调用LLM做增量压缩
    :param valid_messages: 有效历史消息
    :param session_context: Mongo session_context 缓存
    :return: True=需要压缩, False=读缓存或透传即可
    """
    # 步骤1：全局开关关闭则永不压缩
    if not HISTORY_COMPRESS_ENABLED:
        return False
    # 步骤2：有效历史不超过近N条窗口，无需摘要，直接透传原文
    if len(valid_messages) <= HISTORY_RECENT_LIMIT:
        return False

    ctx = session_context or {}
    last_id = ctx.get("last_compressed_msg_id")
    new_count = count_messages_after(valid_messages, last_id)

    # 步骤3：从未生成过摘要，首次超窗必须压缩
    if not ctx.get("session_summary"):
        return True
    # 步骤4：自上次压缩后新增消息达到 chunk 阈值，触发增量更新
    if new_count >= HISTORY_CHUNK_SIZE:
        return True
    # 步骤5：历史总token超阈值，触发压缩（HISTORY_TOKEN_THRESHOLD=0 时跳过此条件）
    if HISTORY_TOKEN_THRESHOLD > 0 and estimate_tokens(valid_messages) > HISTORY_TOKEN_THRESHOLD:
        return True
    return False


def build_recent_only_context(valid_messages: list[dict]) -> str:
    """
    透传模式：仅近N条原文，不含摘要
    :param valid_messages: 有效历史消息
    :return: 历史上下文文本
    """
    recent = valid_messages[-HISTORY_RECENT_LIMIT:]
    return format_messages_text(recent)


def build_with_cached_summary(session_context: dict, valid_messages: list[dict]) -> str:
    """
    摘要模式：Mongo持久化摘要 + 近N条原文
    :param session_context: 会话摘要缓存（session_summary / item_summaries）
    :param valid_messages: 有效历史消息
    :return: 历史上下文文本
    """
    # 步骤1：取滑动窗口内的最近 N 条原文
    recent = valid_messages[-HISTORY_RECENT_LIMIT:]
    recent_text = format_messages_text(recent)
    # 步骤2：读取持久化摘要
    summary = session_context.get("session_summary", "")
    item_summaries = session_context.get("item_summaries") or {}
    item_text = "\n".join(f"{k}: {v}" for k, v in item_summaries.items())
    # 步骤3：拼接为 LLM 可消费的三段式上下文
    parts = ["【历史摘要】", summary]
    if item_text:
        parts.extend(["【按主体摘要】", item_text])
    parts.extend(["【近{}条原文】".format(HISTORY_RECENT_LIMIT), recent_text])
    return "\n".join(parts)


@step_log("incremental_compress")
def incremental_compress(
    session_id: str,
    valid_messages: list[dict],
    session_context: dict | None,
) -> dict:
    """
    调用LLM增量压缩，并将摘要持久化到 Mongo session_context
    :param session_id: 会话ID
    :param valid_messages: 有效历史消息
    :param session_context: 已有摘要缓存
    :return: 更新后的摘要文档
    """
    ctx = session_context or {}
    last_id = ctx.get("last_compressed_msg_id")

    # 步骤1：确定本次待压缩的消息片段（首次压更早部分，后续压边界之后新增）
    to_compress = get_messages_after(valid_messages, last_id)
    if not to_compress and ctx.get("session_summary"):
        return ctx

    # 步骤2：组装 Prompt，带入旧摘要 + 旧主体摘要 + 新消息
    new_messages_text = format_messages_text(to_compress)
    old_item_summaries = json.dumps(ctx.get("item_summaries") or {}, ensure_ascii=False)
    prompt_text = load_prompt(
        "history_compress",
        old_summary=ctx.get("session_summary", "无"),
        old_item_summaries=old_item_summaries,
        new_messages=new_messages_text or "无新消息",
    )

    # 步骤3：LLM 返回 JSON（session_summary + item_summaries）
    json_llm = llm_provider.chat(json_mode=True)
    result = (json_llm | JsonOutputParser()).invoke([HumanMessage(content=prompt_text)])

    # 步骤4：更新压缩边界 = 近N条窗口的前一条消息（该条及更早内容已进入摘要）
    compress_boundary = (
        valid_messages[-(HISTORY_RECENT_LIMIT + 1)]
        if len(valid_messages) > HISTORY_RECENT_LIMIT
        else valid_messages[-1]
    )
    new_ctx = {
        "session_summary": result.get("session_summary", ctx.get("session_summary", "")),
        "item_summaries": result.get("item_summaries", ctx.get("item_summaries", {})),
        "last_compressed_msg_id": str(compress_boundary.get("_id", "")),
        "compressed_at": datetime.now().timestamp(),
        "summary_version": int(ctx.get("summary_version", 0)) + 1,
    }

    # 步骤5：持久化到 Mongo session_context，下次查询直接读缓存
    history_repository.save_session_context(session_id, new_ctx)
    logger.info(f"会话{session_id}历史压缩完成, version={new_ctx['summary_version']}")
    return new_ctx


@step_log("build_history_context")
def build_history_context(session_id: str) -> tuple[str, bool]:
    """
    构建供后续节点使用的历史上下文（核心分支逻辑）
    :param session_id: 会话ID
    :return: (history_context文本, compress_skipped是否跳过LLM压缩)
    """
    # 步骤1：读 Mongo 全量消息 + 过滤有效历史 + 读 session_context 缓存
    all_messages = history_repository.list_all(session_id)
    valid_messages = filter_valid_messages(all_messages)
    session_context = history_repository.get_session_context(session_id)

    # 步骤2：有效历史 <= N 条 → 透传近N条原文，不调LLM
    if len(valid_messages) <= HISTORY_RECENT_LIMIT:
        return build_recent_only_context(valid_messages), True

    # 步骤3：有效历史 > N 条，但未达压缩触发条件 → 读缓存摘要 + 近N条原文
    if not should_compress(valid_messages, session_context):
        ctx = session_context or {}
        if ctx.get("session_summary"):
            return build_with_cached_summary(ctx, valid_messages), True
        # 尚无摘要缓存时，暂时只透传近N条（等下次触发再压）
        return build_recent_only_context(valid_messages), True

    # 步骤4：触发压缩 → LLM增量压缩并持久化 → 拼摘要+近N条原文
    new_ctx = incremental_compress(session_id, valid_messages, session_context)
    return build_with_cached_summary(new_ctx, valid_messages), False


@step_log("compress_history")
def compress_history(state: QueryGraphState) -> QueryGraphState:
    """
    历史压缩节点业务入口，由 node_history_compress 调用
    :param state: 查询图状态
    :return: 写入 history_context / compress_skipped 后的状态
    """
    session_id = state.get("session_id")
    if not session_id:
        raise ValueError("session_id为空,无法进行历史压缩!")

    # 步骤1：按分支构建历史上下文文本
    history_context, compress_skipped = build_history_context(session_id)
    # 步骤2：回写 state，供 node_item_name_confirm / node_answer_output 消费
    state["history_context"] = history_context
    state["compress_skipped"] = compress_skipped
    logger.info(f"历史压缩节点完成, skipped={compress_skipped}")
    return state
