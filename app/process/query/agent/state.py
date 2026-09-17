from typing_extensions import TypedDict
from typing import List
import copy

class QueryGraphState(TypedDict):
    """
    QueryGraphState 定义了整个查询流程中流转的数据结构。
    TypedDict 让我们在代码中能有自动补全和类型检查。
    使用字典式访问（如 state["session_id"]、state.get("answer")）。
    """
    session_id: str  # 会话唯一标识
    original_query: str  # 用户原始问题

    # 检索过程中的中间数据
    embedding_chunks: list  # 普通向量检索回来的切片
    hyde_embedding_chunks: list  # HyDE 检索回来的切片
    web_search_docs: list  # 网络搜索回来的文档

    # 排序过程中的数据
    rrf_chunks: list  # RRF 融合排序后的切片
    reranked_docs: list  # 重排序后的最终 Top-K 文档

    # 生成过程中的数据
    prompt: str  # 组装好的 Prompt
    answer: str  # 最终生成的答案

    # 辅助信息
    item_names: List[str]  # 提取出的商品名称
    rewritten_query: str  # 改写后的问题
    history: list  # 历史对话记录
    history_context: str  # 压缩后的历史上下文文本
    compress_skipped: bool  # 是否跳过LLM压缩
    cache_hit: bool  # 语义缓存是否命中
    is_stream: bool  # 是否流式输出标记
    image_urls: List[str]  # 答案中引用的图片链接
    citations: list  # 引用来源列表
    item_names_roles_dict: List[dict[str, List[str]]]
    denied_item_names: List[str]
    # 鉴权信息
    user_id: str
    roles: List[str]
    department_id: str            # 直属部门（M1-05 四维权限判定用）
    allowed_knowledge_ids: List[str]  # 鉴权放行的知识单元（审计/前端）
    denied_knowledge_ids: List[str]   # 鉴权拦截的知识单元（审计/前端，绝不进提示词）
    skip_cache: bool              # True 时 node_save_cache 跳过写入
    hit_kind: str                 # 命中类型：faq / semantic（缓存短路时）

# ========================
# 默认状态（全部为空）
# ========================
query_graph_default_state: QueryGraphState = {
    "session_id": "",
    "original_query": "",
    "embedding_chunks": [],
    "hyde_embedding_chunks": [],
    "web_search_docs": [],
    "rrf_chunks": [],
    "reranked_docs": [],
    "prompt": "",
    "answer": "",
    "item_names": [],
    "rewritten_query": "",
    "history": [],
    "history_context": "",
    "compress_skipped": True,
    "cache_hit": False,
    "is_stream": False,
    "image_urls": [],
    "citations": [],
    "item_names_roles_dict": [],
    "denied_item_names": [],
    "user_id": "",
    "roles": [],
    "department_id": "",
    "allowed_knowledge_ids": [],
    "denied_knowledge_ids": [],
    "skip_cache": False,
    "hit_kind": "",
}


# ========================
# 创建默认状态（可覆盖）
# ========================
def create_query_default_state(**overrides) -> QueryGraphState:
    """
    创建查询流程的默认状态，支持覆盖字段
    """
    state = copy.deepcopy(query_graph_default_state)
    state.update(overrides)
    return state


# ========================
# 获取干净状态
# ========================
def get_query_default_state() -> QueryGraphState:
    """
    返回一个新的状态实例，避免全局变量污染。
    """
    return copy.deepcopy(query_graph_default_state)


# ========================
# 状态复制函数
# ========================
def copy_query_state(state: QueryGraphState, **overrides) -> QueryGraphState:
    """
    复制现有状态并可覆盖字段，深拷贝，不污染原数据
    """
    new_state = copy.deepcopy(state)
    new_state.update(overrides)
    return new_state
