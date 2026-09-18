import sys

from app.shared.runtime.logger import node_log
from app.rag.query.rrf_service import fuse_by_rrf
from app.shared.utils.node_delay_utils import maybe_node_delay
from app.shared.utils.pipeline_events import emit_skipped, emit_step
from app.shared.utils.task_utils import add_done_task, add_running_task

@node_log("node_rrf")
def node_rrf(state):
    """
    节点功能：Reciprocal Rank Fusion
    将多路召回的结果（向量、HyDE、Web）进行加权融合排序。
    """
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))
    maybe_node_delay()
    try:
        state = fuse_by_rrf(state)
    except ValueError:
        # M1-05：三路检索全空（如知识单元被停用过滤后）优雅返回，不再 500
        state["answer"] = "未在知识库中找到与您问题相关的内容，请换个问法，或联系知识管理员补充对应文档。"
        state["skip_cache"] = True
        emit_step(state["session_id"], "search", "done", "三路检索均为空", state["is_stream"])
        emit_skipped(state["session_id"], ["auth", "compose", "generate"], state["is_stream"])
        add_done_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))
        return state
    emit_step(state["session_id"], "search", "done",
              f"混合检索完成，融合后候选 {len(state.get('rrf_chunks') or [])} 条", state["is_stream"])
    add_done_task(state['session_id'], sys._getframe().f_code.co_name, state.get("is_stream"))
    return state


if __name__ == "__main__":
    mock_state = {
        "session_id": "test_rrf_session",
        "is_stream": False,
        "original_query": "HAK 180 烫金机怎么操作？",
        "rewritten_query": "HAK 180 烫金机的具体操作步骤是什么？",
        "item_names": ["HAK 180 烫金机"],
    }

    from app.process.query.agent.nodes.node_search_embedding import node_search_embedding
    from app.process.query.agent.nodes.node_search_embedding_hyde import node_search_embedding_hyde

    emb_res = node_search_embedding(mock_state)
    hyde_res = node_search_embedding_hyde(mock_state)
    mock_state["embedding_chunks"] = emb_res.get("embedding_chunks") or []
    mock_state["hyde_embedding_chunks"] = hyde_res.get("hyde_embedding_chunks") or []

    result = node_rrf(mock_state)
    print(result)