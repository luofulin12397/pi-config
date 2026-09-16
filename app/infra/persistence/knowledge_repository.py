# -*- coding: utf-8 -*-
"""
知识单元台账（MongoDB knowledge_units 集合）。M1-02

- 知识单元 = 一次成功导入的文档，幂等键为 file_title（与 Milvus kb_chunks 的清理键一致）
- knowledge_id 稳定派生自 file_title（重复导入不产生重复单元）
- enabled=False 的单元在问答检索中被过滤（见两个检索服务的停用过滤）
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.shared.clients.mongo_auth_utils import get_auth_mongo_tool

_FORMAT_BY_EXT = {"pdf": "pdf", "md": "md", "markdown": "md", "doc": "docx", "docx": "docx", "txt": "txt"}

# 台账可编辑字段白名单（update 只接受这些键）
EDITABLE_FIELDS = ("title", "category", "enabled")


def knowledge_id_of(file_title: str) -> str:
    """由 file_title 稳定派生知识单元 ID（幂等）。"""
    return "k" + hashlib.sha1(file_title.encode("utf-8")).hexdigest()[:12]


def _now():
    return datetime.now(timezone.utc)


class KnowledgeRepository:

    def register(
        self,
        *,
        file_title: str,
        item_name: str = "",
        task_id: str = "",
        created_by: str = "",
        chunks_count: int = 0,
        format_ext: str = "",
    ) -> str:
        """导入成功后登记知识单元（按 file_title 幂等 upsert），返回 knowledge_id。"""
        kid = knowledge_id_of(file_title)
        ext = (format_ext or (file_title.rsplit(".", 1)[-1] if "." in file_title else "")).lower() or "txt"
        title = file_title.rsplit(".", 1)[0] if "." in file_title else file_title
        tool = get_auth_mongo_tool()
        tool.knowledge_units.update_one(
            {"knowledge_id": kid},
            {
                "$set": {
                    "knowledge_id": kid,
                    "file_title": file_title,
                    "item_name": item_name,
                    "task_id": task_id,
                    "chunks_count": chunks_count,
                    "updated_at": _now(),
                },
                "$setOnInsert": {
                    "title": title,
                    "format": _FORMAT_BY_EXT.get(ext, ext),
                    "category": "未分类",
                    "enabled": True,  # 仅首次插入设置；重复导入不覆盖管理员的人工配置
                    "created_by": created_by,
                    "created_at": _now(),
                },
            },
            upsert=True,
        )
        return kid

    def list_units(self, kw: str | None = None, category: str | None = None, limit: int = 100) -> list[dict]:
        query: dict = {}
        if kw:
            query["title"] = {"$regex": kw, "$options": "i"}
        if category:
            query["category"] = category
        cursor = (
            get_auth_mongo_tool()
            .knowledge_units.find(query, {"_id": 0})
            .sort("updated_at", -1)
            .limit(limit)
        )
        return list(cursor)

    def get(self, knowledge_id: str) -> dict | None:
        return get_auth_mongo_tool().knowledge_units.find_one(
            {"knowledge_id": knowledge_id}, {"_id": 0}
        )

    def get_by_file_title(self, file_title: str) -> dict | None:
        return get_auth_mongo_tool().knowledge_units.find_one(
            {"file_title": file_title}, {"_id": 0}
        )

    def update(self, knowledge_id: str, patch: dict) -> int:
        """白名单字段更新（title/category/enabled），返回修改文档数。"""
        payload = {k: patch[k] for k in EDITABLE_FIELDS if k in patch}
        if not payload:
            return 0
        payload["updated_at"] = _now()
        result = get_auth_mongo_tool().knowledge_units.update_one(
            {"knowledge_id": knowledge_id}, {"$set": payload}
        )
        return result.modified_count

    def delete(self, knowledge_id: str) -> int:
        result = get_auth_mongo_tool().knowledge_units.delete_one({"knowledge_id": knowledge_id})
        return result.deleted_count

    def disabled_file_titles(self) -> list[str]:
        """已停用知识单元的 file_title 列表（供检索服务过滤）。"""
        cursor = get_auth_mongo_tool().knowledge_units.find(
            {"enabled": False}, {"file_title": 1, "_id": 0}
        )
        return [d["file_title"] for d in cursor if d.get("file_title")]


knowledge_repository = KnowledgeRepository()
