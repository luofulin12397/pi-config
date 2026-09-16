# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 查询图入口节点：语义缓存读（BGE-M3 余弦相似度）

 @dependency cache_service.lookup_semantic_cache

 @output state.answer, state.cache_hit, state.question_embedding, state.image_urls, state.citations(命中时)
"""

import sys

from app.rag.query.cache_service import lookup_semantic_cache
from app.shared.runtime.logger import node_log
from app.shared.utils.node_delay_utils import maybe_node_delay
from app.shared.utils.pipeline_events import emit_skipped, emit_step
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_query_cache")
def node_query_cache(state):
    """
    节点功能：查询语义缓存，命中则直接返回答案，跳过后续检索与 LLM
    入参：state['original_query'], state['session_id'], state['is_stream'], state['user_id']
    出参：state['answer'], state['cache_hit'], state['question_embedding'], state['image_urls'], state['citations']
    """
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    maybe_node_delay()
    state = lookup_semantic_cache(state)
    if state.get("cache_hit"):
        # 命中：语义缓存（M3 将扩展 FAQ 缓存）直接返回，后续步骤标记 skipped
        emit_step(state["session_id"], "faq", "done", "语义缓存命中，直接返回答案", state["is_stream"])
        emit_skipped(state["session_id"], ["context", "search", "auth", "compose", "generate"], state["is_stream"])
    else:
        emit_step(state["session_id"], "faq", "done", "未命中缓存，进入 RAG 链路", state["is_stream"])
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    return state
