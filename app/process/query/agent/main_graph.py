from langgraph.graph import END, StateGraph

from app.process.query.agent.nodes.node_access_control import node_access_control
from app.process.query.agent.nodes.node_answer_output import node_answer_output
from app.process.query.agent.nodes.node_history_compress import node_history_compress
from app.process.query.agent.nodes.node_item_name_confirm import node_item_name_confirm
from app.process.query.agent.nodes.node_query_cache import node_query_cache
from app.process.query.agent.nodes.node_rerank import node_rerank
from app.process.query.agent.nodes.node_perm_filter import node_perm_filter
from app.process.query.agent.nodes.node_rrf import node_rrf
from app.process.query.agent.nodes.node_save_cache import node_save_cache
from app.process.query.agent.nodes.node_search_embedding import node_search_embedding
from app.process.query.agent.nodes.node_search_embedding_hyde import node_search_embedding_hyde
from app.process.query.agent.nodes.node_web_search_mcp import node_web_search_mcp
from app.process.query.agent.state import QueryGraphState, create_query_default_state
from app.shared.runtime.logger import logger

query_graph_builder = StateGraph(QueryGraphState)


# 2. 添加节点（11 个）
query_graph_builder.add_node("node_query_cache", node_query_cache)
query_graph_builder.add_node("node_history_compress", node_history_compress)
query_graph_builder.add_node("node_item_name_confirm", node_item_name_confirm)
query_graph_builder.add_node("node_access_control", node_access_control)
query_graph_builder.add_node("node_search_embedding", node_search_embedding)
query_graph_builder.add_node("node_search_embedding_hyde", node_search_embedding_hyde)
query_graph_builder.add_node("node_web_search_mcp", node_web_search_mcp)
query_graph_builder.add_node("node_rrf", node_rrf)
query_graph_builder.add_node("node_rerank", node_rerank)
query_graph_builder.add_node("node_perm_filter", node_perm_filter)
query_graph_builder.add_node("node_answer_output", node_answer_output)
query_graph_builder.add_node("node_save_cache", node_save_cache)

# 3. 入口：语义缓存读 → 命中 END / 未命中 history_compress
query_graph_builder.set_entry_point("node_query_cache")


def node_query_cache_after(state: QueryGraphState):
    """语义缓存命中则直接结束，未命中则进入历史压缩。"""
    if state.get("cache_hit"):
        logger.info("语义缓存命中，跳过后续 RAG 流程")
        return END
    logger.info("语义缓存未命中，进入历史压缩与 RAG 检索流程")
    return "node_history_compress"


query_graph_builder.add_conditional_edges(
    "node_query_cache",
    node_query_cache_after,
    {
        END: END,
        "node_history_compress": "node_history_compress",
    },
)

# 4. 历史压缩 → 主体识别 → 权限校验
query_graph_builder.add_edge("node_history_compress", "node_item_name_confirm")
query_graph_builder.add_edge("node_item_name_confirm", "node_access_control")


def node_access_control_after(state: QueryGraphState):
    if state.get("answer"):
        logger.info(f"本次没有明确的item_name,提前结束,待用户确定! {state.get('answer')}")
        return "node_answer_output"
    logger.info(f"有明确的item_names :{state.get('item_names')}业务继续进行即可!!")
    return "node_search_embedding", "node_search_embedding_hyde", "node_web_search_mcp"


query_graph_builder.add_conditional_edges(
    "node_access_control",
    node_access_control_after,
    {
        "node_answer_output": "node_answer_output",
        "node_search_embedding": "node_search_embedding",
        "node_search_embedding_hyde": "node_search_embedding_hyde",
        "node_web_search_mcp": "node_web_search_mcp",
    },
)

# 5. 三路检索并行 → RRF → rerank → 生成答案 → 写缓存 → END
query_graph_builder.add_edge("node_search_embedding", "node_rrf")
query_graph_builder.add_edge("node_search_embedding_hyde", "node_rrf")
query_graph_builder.add_edge("node_web_search_mcp", "node_rrf")
query_graph_builder.add_edge("node_rrf", "node_rerank")
# M1-05：精排后先做四维权限过滤（仅放行切片进入提示词组装）
query_graph_builder.add_edge("node_rerank", "node_perm_filter")
query_graph_builder.add_edge("node_perm_filter", "node_answer_output")
query_graph_builder.add_edge("node_answer_output", "node_save_cache")
query_graph_builder.add_edge("node_save_cache", END)

# 6. 编译图对象
query_graph_app = query_graph_builder.compile()

if __name__ == "__main__":
    state = create_query_default_state(
        session_id="1231232132",
        rewritten_query="",
        item_names=[],
        is_stream=True,
        user_id="123123123",
        roles=["common_user"],
        original_query="HAK 180 烫金机的使用注意实现",
    )
    query_graph_app.invoke(state)
