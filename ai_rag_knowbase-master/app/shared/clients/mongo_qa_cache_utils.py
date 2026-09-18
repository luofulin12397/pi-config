# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description MongoDB QA 语义缓存集合工具，复用 HistoryMongoTool 连接

 @dependency mongo_history_utils.get_history_mongo_tool

 @output qa_cache 集合读写
"""

from datetime import datetime
from typing import Any

from bson import ObjectId

from app.shared.clients.mongo_history_utils import get_history_mongo_tool
from app.shared.runtime.logger import logger

_qa_cache_initialized = False


def _get_qa_cache_collection():
    """
    获取 qa_cache 集合并确保 TTL 索引已创建
    :return: pymongo Collection 对象
    """
    global _qa_cache_initialized
    mongo_tool = get_history_mongo_tool()
    collection = mongo_tool.db["qa_cache"]

    # 步骤1：首次访问时创建索引（幂等）
    if not _qa_cache_initialized:
        collection.create_index("expire_time", expireAfterSeconds=0)
        collection.create_index([("knowledge_version", 1)])
        _qa_cache_initialized = True
        logger.info("qa_cache 集合 TTL 索引初始化完成")

    return collection


def delete_cache_by_version(knowledge_version: str) -> int:
    """删除指定知识库版本的全部缓存记录（知识单元停用/删除时调用），返回删除条数"""
    result = _get_qa_cache_collection().delete_many({"knowledge_version": knowledge_version})
    return result.deleted_count


def list_cache_by_version(knowledge_version: str) -> list[dict[str, Any]]:
    """
    查询指定知识库版本下的全部缓存记录
    :param knowledge_version: 版本号
    :return: 文档列表，失败返回空列表
    """
    collection = _get_qa_cache_collection()
    try:
        return list(collection.find({"knowledge_version": knowledge_version}))
    except Exception as e:
        logger.error(f"查询 qa_cache 失败: {e}")
        return []


def insert_cache_entry(document: dict[str, Any]) -> str:
    """
    写入一条缓存记录
    :param document: 完整缓存文档
    :return: 插入文档的 _id 字符串
    """
    collection = _get_qa_cache_collection()
    result = collection.insert_one(document)
    return str(result.inserted_id)


def increment_hit_count(cache_id: str) -> None:
    """
    缓存命中时递增 hit_count 并更新 last_hit_time
    :param cache_id: 文档 _id 字符串
    :return: None
    """
    collection = _get_qa_cache_collection()
    now = datetime.utcnow()
    try:
        collection.update_one(
            {"_id": ObjectId(cache_id)},
            {
                "$inc": {"hit_count": 1},
                "$set": {"last_hit_time": now},
            },
        )
    except Exception as e:
        logger.error(f"更新 qa_cache 命中统计失败, id={cache_id}: {e}")
