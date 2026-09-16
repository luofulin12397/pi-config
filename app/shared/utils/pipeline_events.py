# -*- coding: utf-8 -*-
"""
问答管线 SSE 事件流（M1-06）。

将 LangGraph 查询节点的执行进度映射为契约事件（docs/api-contract.md §0）：
- step:  六个逻辑步骤 faq/context/search/auth/compose/generate，状态 running/done/skipped + detail
- delta: LLM 流式增量（answer_service 已有）
- refs:  引用溯源 + 拦截数（node_answer_output 产出后）
- done:  来源/耗时/token（invoke_query_graph 完成时）

节点 → 逻辑步骤映射（NODE_TO_STEP）：无映射的节点（如 web_search 并行路）不单独发事件，
由 search 步骤统一覆盖。
"""
from app.shared.utils.sse_utils import SSEEvent, push_to_session

STEP_KEYS = ("faq", "context", "search", "auth", "compose", "generate")

# LangGraph 节点名 → 六步逻辑步骤
NODE_TO_STEP = {
    "node_query_cache": "faq",
    "node_history_compress": "context",
    "node_item_name_confirm": "context",
    "node_search_embedding": "search",
    "node_search_embedding_hyde": "search",
    "node_web_search_mcp": "search",
    "node_rrf": "search",
    "node_perm_filter": "auth",
    "node_answer_output": "compose",
    "node_save_cache": "generate",
}


def emit_step(session_id: str, key: str, status: str, detail: str = "", is_stream: bool = False):
    """推送单条 step 事件（队列不存在时 push_to_session 自动丢弃，安全）。"""
    push_to_session(session_id, SSEEvent.STEP, {"key": key, "status": status, "detail": detail})


def emit_step_by_node(session_id: str, node_name: str, status: str, detail: str = "", is_stream: bool = False):
    """按 LangGraph 节点名推送对应逻辑步骤事件（无映射的节点忽略）。"""
    key = NODE_TO_STEP.get(node_name)
    if key:
        emit_step(session_id, key, status, detail, is_stream)


def emit_skipped(session_id: str, keys, is_stream: bool = False):
    """短路场景：把未执行的步骤批量标记 skipped。"""
    for key in keys:
        emit_step(session_id, key, "skipped", "", is_stream)


def emit_refs(session_id: str, citations: list, denied_count: int, is_stream: bool = False):
    """引用溯源 + 拦截数。"""
    push_to_session(session_id, SSEEvent.REFS, {"refs": citations or [], "deniedCount": denied_count})


def emit_done(session_id: str, source: str, latency_ms: int, tokens: int, is_stream: bool = False):
    """完成事件：来源（semantic-cache/rag/denied/no-result）/耗时/token 估算。"""
    push_to_session(session_id, SSEEvent.DONE,
                    {"source": source, "latency": latency_ms, "tokens": tokens})
