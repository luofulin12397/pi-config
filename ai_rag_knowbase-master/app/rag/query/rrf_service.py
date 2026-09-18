from app.process.query.agent.state import QueryGraphState
from app.rag.query.config import RRF_FUSION_LIMIT, RRF_FUSION_K
from app.shared.runtime.logger import logger, step_log


@step_log("get_data_and_validate")
def get_data_and_validate(state):
    """
    获取向量检索两路数据；允许单路为空，与 rerank 容错逻辑对齐。
    """
    embedding_chunks = state.get("embedding_chunks", [])
    hyde_embedding_chunks = state.get("hyde_embedding_chunks", [])
    web_search_docs = state.get("web_search_docs", [])

    has_vector = len(embedding_chunks) > 0 or len(hyde_embedding_chunks) > 0
    has_web = len(web_search_docs) > 0
    if not has_vector and not has_web:
        logger.error("embedding/hyde/web 检索均为空,无法继续业务!")
        raise ValueError("embedding/hyde/web 检索均为空,无法继续业务!")
    return embedding_chunks, hyde_embedding_chunks

@step_log("use_rrf_chunks_list")
def use_rrf_chunks_list(chunks_list: list[tuple[float, list]], limit: int = 5, k: int = 60):
    """
    带有权重思维的 RRF 算法；空路跳过。
    """
    if not chunks_list:
        return []

    score_dict: dict[str, float] = {}
    chunk_dict: dict[str, dict] = {}
    for weight, current_chunks in chunks_list:
        if not current_chunks:
            continue
        for rank, chunk in enumerate(current_chunks, start=1):
            chunk_id = chunk.get("chunk_id")
            if not chunk_id:
                continue
            score_dict[chunk_id] = score_dict.get(chunk_id, 0) + weight * (1 / (k + rank))
            chunk_dict.setdefault(chunk_id, chunk)

    if not score_dict:
        return []

    chunk_list = []
    for chunk_id, score in score_dict.items():
        chunk = chunk_dict.get(chunk_id)
        if chunk is None:
            continue
        chunk["score"] = score
        chunk_list.append(chunk)

    chunk_list.sort(key=lambda x: x["score"], reverse=True)
    return chunk_list[:limit]




@step_log("fuse_by_rrf")
def fuse_by_rrf(state: QueryGraphState):
    """
    RRF 融合：有几路融几路；向量两路皆空时 rrf_chunks=[]，由 rerank 依赖 web 结果。
    """
    embedding_chunks, hyde_embedding_chunks = get_data_and_validate(state)

    chunks_list = []
    if embedding_chunks:
        chunks_list.append((1.0, embedding_chunks))
    if hyde_embedding_chunks:
        chunks_list.append((1.0, hyde_embedding_chunks))

    rrf_chunks = use_rrf_chunks_list(chunks_list, limit=RRF_FUSION_LIMIT, k=RRF_FUSION_K)
    state["rrf_chunks"] = rrf_chunks
    return state