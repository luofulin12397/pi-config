# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 语义缓存配置，读取 QA Cache 相关环境变量

 @dependency common.env_str / env_float

 @output cache_config 全局单例
"""

from dataclasses import dataclass

from app.shared.config.common import env_float, env_str


@dataclass
class CacheConfig:
    """语义缓存运行时配置"""
    knowledge_version: str   # 知识库版本，缓存按版本隔离
    cache_threshold: float   # 余弦相似度命中阈值，默认 0.92
    cache_expire_days: int    # 缓存 TTL 天数，Mongo expire_time 索引过期


def _env_int(name: str, default: int = 0) -> int:
    """
    读取整型环境变量
    :param name: 变量名
    :param default: 默认值
    :return: 整型配置值
    """
    value = env_float(name, float(default))
    return int(value)


# KNOWLEDGE_VERSION：知识库发版后需更新，旧版本缓存自动隔离
# CACHE_THRESHOLD：越高越严格，误命中少但命中率低
# CACHE_EXPIRE_DAYS：qa_cache 文档过期天数
cache_config = CacheConfig(
    knowledge_version=env_str("KNOWLEDGE_VERSION", "v1"),
    cache_threshold=env_float("CACHE_THRESHOLD", 0.92),
    cache_expire_days=_env_int("CACHE_EXPIRE_DAYS", 30),
)
