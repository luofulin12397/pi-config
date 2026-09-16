# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description QA 语义缓存仓储层，封装 Mongo qa_cache 集合读写

 @dependency mongo_qa_cache_utils, cache_config

 @output 缓存文档列表 / 新文档 ID
"""

from datetime import datetime, timedelta
from typing import Any

from app.shared.clients.mongo_qa_cache_utils import (
    delete_cache_by_version,
    increment_hit_count,
    insert_cache_entry,
    list_cache_by_version,
)
from app.shared.config.cache_config import cache_config


class QaCacheRepository:
    def list_by_version(self, knowledge_version: str | None = None) -> list[dict[str, Any]]:
        """
        按知识库版本查询全部缓存记录
        :param knowledge_version: 版本号，空则读配置 KNOWLEDGE_VERSION
        :return: qa_cache 文档列表
        """
        version = knowledge_version or cache_config.knowledge_version
        return list_cache_by_version(version)

    def delete_by_version(self, knowledge_version: str | None = None) -> int:
        """
        清空指定知识库版本的全部语义缓存（M1-02：知识单元停用/删除时调用，
        使缓存中的旧答案立即失效，避免停用/删除后仍返回缓存内容）
        :return: 删除的缓存条数
        """
        version = knowledge_version or cache_config.knowledge_version
        return delete_cache_by_version(version)

    def save(
        self,
        *,
        question: str,
        question_embedding: list[float],
        answer: str,
        image_urls: list[str] | None = None,
        citations: list[dict] | None = None,
        knowledge_version: str | None = None,
    ) -> str:
        """
        写入一条语义缓存记录
        :param question: 原始问题
        :param question_embedding: 问题稠密向量
        :param answer: 完整答案文本
        :param image_urls: 答案关联图片 URL 列表
        :param citations: 引用来源列表
        :param knowledge_version: 知识库版本
        :return: 新文档 _id 字符串
        """
        now = datetime.utcnow()
        expire_days = cache_config.cache_expire_days
        document = {
            "question": question,
            "question_embedding": question_embedding,
            "answer": answer,
            "image_urls": image_urls or [],
            "citations": citations or [],
            "knowledge_version": knowledge_version or cache_config.knowledge_version,
            "hit_count": 0,
            "last_hit_time": now,
            "create_time": now,
            "expire_time": now + timedelta(days=expire_days),
        }
        return insert_cache_entry(document)

    def record_hit(self, cache_id: str) -> None:
        """
        缓存命中时更新命中统计
        :param cache_id: qa_cache 文档 _id
        :return: None
        """
        increment_hit_count(cache_id)


qa_cache_repository = QaCacheRepository()
