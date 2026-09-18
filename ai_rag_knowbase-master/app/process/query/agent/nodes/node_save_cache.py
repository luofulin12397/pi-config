# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 查询图尾节点：语义缓存写（完整 RAG 完成后）

 @dependency cache_service.save_semantic_cache

 @output 无状态字段变更（副作用写入 Mongo qa_cache）
"""

import sys

from app.rag.query.cache_service import save_semantic_cache
from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_save_cache")
def node_save_cache(state):
    """
    节点功能：RAG 流程完成后，将问答结果写入语义缓存
    入参：state['original_query'], state['answer'], state['image_urls'],
          state['question_embedding'], state['reranked_docs'], state['cache_hit']
    出参：state（原样返回，写入 qa_cache 为副作用）
    """
    # 步骤1：登记节点开始，前端 done_list 可展示「语义缓存写入」
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])

    # 步骤2：调用缓存写入服务（核心逻辑在 cache_service）
    #   2.1 cache_hit=True → 跳过（本次答案来自缓存，不重复写入）
    #   2.2 answer 为空 → 跳过
    #   2.3 无 reranked_docs → 跳过（非完整 RAG，如主体追问早退）
    #   2.4 完整 RAG：写入 question/answer/image_urls/question_embedding 到 qa_cache
    state = save_semantic_cache(state)

    # 步骤3：登记节点完成，图流转至 END
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    return state
