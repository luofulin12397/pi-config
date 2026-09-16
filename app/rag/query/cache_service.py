# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 语义缓存服务：基于问题向量余弦相似度查找/写入 QA 缓存

 @dependency qa_cache_repository, history_repository, llm_provider

 @output state.cache_hit / state.answer / state.image_urls（读缓存）
"""

from __future__ import annotations

import numpy as np

from app.infra.llm.providers import llm_provider
from app.infra.persistence.history_repository import history_repository
from app.infra.persistence.qa_cache_repository import qa_cache_repository
from app.process.query.agent.state import QueryGraphState
from app.rag.query.answer_service import parse_image_block_from_answer
from app.shared.config.cache_config import cache_config
from app.shared.runtime.logger import logger, step_log
from app.shared.utils.sse_utils import SSEEvent
from app.shared.utils.task_utils import push_to_session


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    计算两个向量的余弦相似度
    :param vec_a: 向量 A（BGE-M3 已 L2 归一化，点积即余弦相似度）
    :param vec_b: 向量 B
    :return: 相似度分数 0~1
    """
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _encode_question(question: str) -> list[float]:
    """
    为问题生成稠密向量
    :param question: 用户原始问题
    :return: BGE-M3 dense embedding 列表
    """
    embedding_result = llm_provider.embed_documents([question])
    return embedding_result["dense"][0]


def _push_cached_answer_stream(state: QueryGraphState, answer: str) -> None:
    """
    流式模式下逐字推送缓存答案
    :param state: 查询图状态
    :param answer: 缓存中的完整答案
    :return: None
    """
    if not state.get("is_stream"):
        return
    for ch in answer:
        push_to_session(state["session_id"], SSEEvent.DELTA, {"delta": ch})


def _resolve_cached_citations(cache_entry: dict) -> list[dict]:
    """
    从缓存记录恢复 citations
    :param cache_entry: qa_cache 文档
    :return: citations 列表
    """
    return cache_entry.get("citations") or []


def _save_cache_hit_history(state: QueryGraphState) -> None:
    """
    缓存命中时补写用户提问与助手回复到 chat_message
    :param state: 查询图状态（含 answer/image_urls/citations）
    :return: None
    """
    question = state.get("original_query", "")
    user_id = state.get("user_id", "")
    history_repository.save_message(
        session_id=state.get("session_id"),
        user_id=user_id,
        role="user",
        text=question,
        rewritten_query=question,
        item_names=state.get("item_names") or [],
    )
    history_repository.save_message(
        session_id=state.get("session_id"),
        user_id=user_id,
        role="assistant",
        text=state.get("answer", ""),
        rewritten_query=question,
        item_names=state.get("item_names") or [],
        image_urls=state.get("image_urls") or [],
        citations=state.get("citations") or [],
    )


def _resolve_cached_image_urls(cache_entry: dict) -> list[str]:
    """
    从缓存记录恢复图片 URL，旧数据无 image_urls 时从 answer 解析
    :param cache_entry: qa_cache 文档
    :return: 图片 URL 列表
    """
    cached_urls = cache_entry.get("image_urls") or []
    if cached_urls:
        return cached_urls
    # 兼容旧缓存：从 answer【图片】区块 fallback 解析
    return parse_image_block_from_answer(cache_entry.get("answer", ""))


@step_log("lookup_semantic_cache")
def lookup_semantic_cache(state: QueryGraphState) -> QueryGraphState:
    """
    查询语义缓存，命中则直接返回答案
    :param state: 查询图状态
    :return: 更新 cache_hit/answer/image_urls/question_embedding 后的 state
    """
    # 步骤1：校验 original_query，空则跳过缓存
    question = state.get("original_query", "")
    if not question:
        logger.warning("original_query 为空，跳过语义缓存查询")
        state["cache_hit"] = False
        state["question_embedding"] = []
        return state

    # 步骤2：生成问题 embedding，写入 state 供未命中时 node_save_cache 复用
    query_embedding = _encode_question(question)
    state["question_embedding"] = query_embedding

    # 步骤3：按 knowledge_version 拉取 qa_cache 全量记录
    cache_entries = qa_cache_repository.list_by_version()
    if not cache_entries:
        logger.info(
            f"语义缓存未命中: 当前版本 {cache_config.knowledge_version} 无缓存记录"
        )
        state["cache_hit"] = False
        return state

    # 步骤4：遍历缓存条目，找余弦相似度最高的一条
    best_score = -1.0
    best_entry: dict | None = None
    for entry in cache_entries:
        cached_embedding = entry.get("question_embedding")
        if not cached_embedding:
            continue
        score = _cosine_similarity(query_embedding, cached_embedding)
        if score > best_score:
            best_score = score
            best_entry = entry

    # 步骤5：判断是否达到 CACHE_THRESHOLD，命中则回填 state 并写历史
    threshold = cache_config.cache_threshold
    if best_entry and best_score >= threshold:
        cache_id = str(best_entry["_id"])
        logger.info(
            f"语义缓存命中: question='{best_entry.get('question')}', "
            f"score={best_score:.4f}, threshold={threshold}, cache_id={cache_id}"
        )
        state["answer"] = best_entry["answer"]
        state["image_urls"] = _resolve_cached_image_urls(best_entry)
        state["citations"] = _resolve_cached_citations(best_entry)
        state["cache_hit"] = True
        qa_cache_repository.record_hit(cache_id)
        _push_cached_answer_stream(state, state["answer"])
        _save_cache_hit_history(state)
        logger.info(f"语义缓存命中图片数量: {len(state.get('image_urls', []))}")
        return state

    # 步骤6：未命中，记录 best_score 日志，继续后续 RAG 流程
    logger.info(
        f"语义缓存未命中: best_score={best_score:.4f}, threshold={threshold}, "
        f"question='{question}'"
    )
    state["cache_hit"] = False
    return state


@step_log("save_semantic_cache")
def save_semantic_cache(state: QueryGraphState) -> QueryGraphState:
    """
    将完整 RAG 问答结果写入语义缓存
    :param state: 查询图状态
    :return: 原样返回 state
    """
    # 步骤1：缓存命中场景不重复写入
    if state.get("cache_hit"):
        logger.info("本次为缓存命中，跳过写入语义缓存")
        return state

    # 步骤2：无答案不写入
    answer = state.get("answer", "")
    if not answer:
        logger.info("answer 为空，跳过写入语义缓存")
        return state

    # 步骤3：无 reranked_docs 表示非完整 RAG（如主体追问早退），不写入
    reranked_docs = state.get("reranked_docs") or []
    if not reranked_docs:
        logger.info("无 reranked_docs（非完整 RAG 流程），跳过写入语义缓存")
        return state

    # 步骤4：复用读缓存时生成的 question_embedding，避免重复 embedding
    question = state.get("original_query", "")
    question_embedding = state.get("question_embedding") or []
    if not question_embedding:
        question_embedding = _encode_question(question)

    # 步骤5：写入 Mongo qa_cache（含 answer + image_urls + TTL）
    cache_id = qa_cache_repository.save(
        question=question,
        question_embedding=question_embedding,
        answer=answer,
        image_urls=state.get("image_urls") or [],
        citations=state.get("citations") or [],
    )
    logger.info(
        f"语义缓存写入成功: cache_id={cache_id}, question='{question}', "
        f"image_count={len(state.get('image_urls') or [])}, "
        f"citation_count={len(state.get('citations') or [])}, "
        f"version={cache_config.knowledge_version}, expire_days={cache_config.cache_expire_days}"
    )
    return state
