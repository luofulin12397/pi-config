# -*- coding: utf-8 -*-
# @Time : 2026/06/13

"""
 @description 查询图入口节点：FAQ 缓存匹配（M3-02，优先）→ 语义缓存读

 @dependency faq_repository, cache_service.lookup_semantic_cache

 @output state.answer, state.cache_hit, state.hit_kind, state.image_urls, state.citations(命中时)
"""

import sys

from app.infra.persistence.faq_repository import faq_repository
from app.rag.query.cache_service import lookup_semantic_cache
from app.shared.runtime.logger import node_log
from app.shared.utils.node_delay_utils import maybe_node_delay
from app.shared.utils.pipeline_events import emit_skipped, emit_step
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_query_cache")
def node_query_cache(state):
    """
    节点功能：两级缓存匹配——FAQ 缓存（人工审核发布，优先）→ 语义缓存（自动）
    命中任一即直接返回答案，跳过后续检索与 LLM。

    FAQ 匹配异常不阻断流程（降级进入语义缓存/检索链路）。
    """
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    maybe_node_delay()

    # ---- M3-02：FAQ 缓存优先（人工审核发布的标准答案，命中即毫秒直出）----
    try:
        faq = faq_repository.match(state.get("original_query", ""))
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").warning(f"FAQ 缓存匹配异常（降级为语义缓存/检索）: {exc!r}")
        faq = None
    if faq:
        state["answer"] = faq["answer"]
        state["cache_hit"] = True
        state["hit_kind"] = "faq"
        faq_repository.record_hit(faq["faq_id"])
        emit_step(state["session_id"], "faq", "done",
                  f"FAQ 缓存命中「{faq['question']}」（相似度 {int(faq['sim'] * 100)}%），毫秒直出",
                  state["is_stream"])
        emit_skipped(state["session_id"], ["context", "search", "auth", "compose", "generate"],
                     state["is_stream"])
        add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
        return state

    maybe_node_delay()
    state = lookup_semantic_cache(state)
    if state.get("cache_hit"):
        state["hit_kind"] = "semantic"
        emit_step(state["session_id"], "faq", "done", "语义缓存命中，直接返回答案", state["is_stream"])
        emit_skipped(state["session_id"], ["context", "search", "auth", "compose", "generate"],
                     state["is_stream"])
    else:
        emit_step(state["session_id"], "faq", "done", "未命中缓存，进入 RAG 链路", state["is_stream"])
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    return state
