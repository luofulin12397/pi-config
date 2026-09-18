# -*- coding: utf-8 -*-
"""
Embedding 服务（M1 联调 API 化）。

历史实现为本地 BGEM3EmbeddingFunction（torch + 模型权重，约 2GB 下载）；现改为：
- dense：硅基流动 OpenAI 兼容 /v1/embeddings 端点（BAAI/bge-m3，1024 维）
- sparse：本地确定性字符 n-gram 词频哈希（纯标准库），形状与原 BGE-M3 sparse 兼容
  （{维度索引: 权重}）。近似实现仅用于联调/演示，混合检索精度由 rerank API 精排兜底。

输出形状与原实现一致：{'dense': [[...], ...], 'sparse': [{idx: weight}, ...]}
"""
from __future__ import annotations

import hashlib
import math

import httpx

from app.shared.config.embedding_config import embedding_config
from app.shared.runtime.logger import logger

_SPARSE_DIM = 30000  # 稀疏哈希空间上界（文档/查询共用同一映射保证一致性）
_client = httpx.Client(timeout=30)


def get_bge_m3_ef():
    """废弃：API 化后不再有本地 BGEM3EmbeddingFunction 实例。保留符号兼容旧 import，勿在新代码中使用。"""
    logger.warning("get_bge_m3_ef 已废弃（embedding 已 API 化），返回 None")
    return None


def _sparse_vector(text: str) -> dict[int, float]:
    """确定性字符 n-gram 词频哈希稀疏向量（单字 + 二元组，子线性权重）。"""
    tokens = "".join(str(text).lower().split())
    tf: dict[int, float] = {}
    for i, ch in enumerate(tokens):
        idx = int.from_bytes(hashlib.md5(ch.encode("utf-8")).digest()[:4], "big") % _SPARSE_DIM
        tf[idx] = tf.get(idx, 0.0) + 1.0
        if i + 1 < len(tokens):
            bigram = tokens[i : i + 2]
            idx = int.from_bytes(hashlib.md5(bigram.encode("utf-8")).digest()[:4], "big") % _SPARSE_DIM
            tf[idx] = tf.get(idx, 0.0) + 1.0
    return {idx: round(1.0 + math.log(cnt), 6) for idx, cnt in tf.items()}


def _dense_via_api(texts: list[str]) -> list[list[float]]:
    """调用 OpenAI 兼容 embeddings 端点，按输入顺序返回向量列表。

    免费端点高峰期偶发 503/429，做 3 次指数退避重试（ISS-003）。
    """
    import time

    last_err: Exception | None = None
    for attempt in range(5):
        try:
            resp = _client.post(
                f"{embedding_config.api_base}/embeddings",
                headers={"Authorization": f"Bearer {embedding_config.api_key}"},
                json={"model": embedding_config.api_model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda item: item["index"])
            return [item["embedding"] for item in data]
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_err = exc
            status = getattr(getattr(exc, "response", None), "status_code", 0)
            if status and status not in (429, 500, 502, 503, 504):
                raise
            wait = 1.0 * (2**attempt)
            logger.warning(f"embeddings 端点瞬时失败({status or type(exc).__name__})，{wait:.0f}s 后重试({attempt + 1}/5)")
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


def generate_embeddings(texts: list[str]) -> dict[str, list]:
    """
    生成稠密 + 稀疏向量。
    :param texts: 文本列表
    :return: {'dense': [[...]], 'sparse': [{维度: 权重}, ...]}
    """
    if not texts:
        return {"dense": [], "sparse": []}
    dense = _dense_via_api(texts)
    sparse = [_sparse_vector(t) for t in texts]
    logger.debug(f"embedding 完成：{len(texts)} 条（API dense {len(dense[0])} 维 + 本地 sparse）")
    return {"dense": dense, "sparse": sparse}
