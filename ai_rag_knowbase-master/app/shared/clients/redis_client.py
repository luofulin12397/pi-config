"""Redis 客户端；未配置 REDIS_URL 时返回 None，回退内存存储。"""
import os
from typing import Any

from app.shared.runtime.logger import logger

_redis_client: Any = None
_redis_checked = False


def get_redis_client():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis

        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis 连接成功，任务/SSE 将使用 Redis 后端")
    except Exception as exc:
        logger.warning(f"Redis 不可用，回退内存存储: {exc}")
        _redis_client = None
    return _redis_client


def redis_enabled() -> bool:
    return get_redis_client() is not None
