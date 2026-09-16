# -*- coding: utf-8 -*-
"""
Reranker 服务（M1 联调 API 化）。

历史实现为本地 FlagReranker（torch + 模型权重）；现改为硅基流动 /rerank 端点
（BAAI/bge-reranker-v2-m3）。对外保持 compute_score(pairs, normalize=True) 调用形状
兼容（rerank_service 无需改动），输入 pairs 为 [[query, document], ...]。
"""
from __future__ import annotations

import httpx

from app.shared.config.reranker_config import reranker_config
from app.shared.runtime.logger import logger

_client = httpx.Client(timeout=30)


class _ApproxTokenizer:
    """近似 tokenizer：按字符返回序列（中文 1 字 ≈ 1 token 量级）。

    rerank_service 用它做超长文本裁剪的长度估算，encode 返回值只被 len() 消费。
    """

    def encode(self, text: str, add_special_tokens: bool = False) -> list[str]:
        return list(text or "")


class SiliconFlowReranker:
    """形状兼容 FlagReranker.compute_score 的 API 重排器。"""

    def compute_score(self, pairs: list[list], normalize: bool = True) -> list[float]:
        """对 [[query, document], ...] 逐对打分，返回与输入顺序一致的分数列表。"""
        if not pairs:
            return []

        # 按 query 分组批量调用（同一 query 的 documents 一次请求）
        groups: dict[str, list[int]] = {}
        for i, pair in enumerate(pairs):
            query, _doc = pair[0], pair[1]
            groups.setdefault(query, []).append(i)

        scores = [0.0] * len(pairs)
        for query, index_list in groups.items():
            documents = [pairs[i][1] for i in index_list]
            resp = _client.post(
                f"{reranker_config.api_base}/rerank",
                headers={"Authorization": f"Bearer {reranker_config.api_key}"},
                json={
                    "model": reranker_config.api_model,
                    "query": query,
                    "documents": documents,
                },
            )
            resp.raise_for_status()
            for item in resp.json()["results"]:
                scores[index_list[item["index"]]] = float(item["relevance_score"])

        if normalize:
            lo, hi = min(scores), max(scores)
            if hi > lo:
                scores = [(s - lo) / (hi - lo) for s in scores]
            else:
                scores = [0.0 for _ in scores]
        return scores


_reranker_model: SiliconFlowReranker | None = None


def get_reranker_model() -> SiliconFlowReranker:
    """获取重排器单例（API 版，无本地模型加载）。"""
    global _reranker_model
    if _reranker_model is None:
        logger.info("初始化重排器（硅基流动 API 模式）")
        _reranker_model = SiliconFlowReranker()
        _reranker_model.tokenizer = _ApproxTokenizer()
    return _reranker_model
