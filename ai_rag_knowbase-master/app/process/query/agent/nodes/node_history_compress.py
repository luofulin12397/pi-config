# -*- coding: utf-8 -*-
# @Time : 2026/06/12
# @Author : lzm

"""
 @description 查询图节点：历史上下文压缩（阈值触发，默认透传）

 @dependency history_compress_service.compress_history

 @output state.history_context, state.compress_skipped
"""

import sys

from app.rag.query.history_compress_service import compress_history
from app.shared.runtime.logger import node_log
from app.shared.utils.node_delay_utils import maybe_node_delay
from app.shared.utils.pipeline_events import emit_step
from app.shared.utils.task_utils import add_done_task, add_running_task


@node_log("node_history_compress")
def node_history_compress(state):
    """
    节点功能：为后续主体识别/答案生成准备历史上下文
    入参：state['session_id'], state['is_stream']
    出参：state['history_context'] 拼接后的历史文本
          state['compress_skipped']  True=未调LLM压缩, False=本次执行了增量压缩
    """
    # 步骤1：登记节点开始，前端 done_list / SSE 进度可展示「历史上下文压缩」
    add_running_task(state["session_id"], "node_history_compress", state["is_stream"])

    # 步骤2：调用压缩服务（核心逻辑在 history_compress_service）
    #   2.1 从 Mongo chat_message 读取该 session 全部消息，过滤 item_names 非空的有效历史
    #   2.2 有效历史 <= HISTORY_RECENT_LIMIT(默认10)：
    #       透传模式，仅取近 N 条原文拼成 history_context，不调 LLM
    #   2.3 有效历史 > 10 条，且 should_compress 为 False：
    #       读 Mongo session_context 已有摘要 + 近 N 条原文拼成 history_context，不调 LLM
    #   2.4 有效历史 > 10 条，且 should_compress 为 True（无摘要/新增>=4条/token超阈值）：
    #       调用 incremental_compress → LLM 增量压缩 → 摘要持久化到 session_context
    #       再拼「摘要 + 近 N 条原文」写入 history_context
    #   2.5 compress_skipped=True 表示本次未调 LLM；False 表示本次做了增量压缩
    maybe_node_delay()
    state = compress_history(state)
    emit_step(state["session_id"], "context", "done", "多轮历史已压缩为摘要上下文", state["is_stream"])

    # 步骤3：登记节点完成，供前端展示节点流转进度
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])

    # 步骤4：将 state 交给下一节点 node_item_name_confirm（消费 history_context）
    return state
