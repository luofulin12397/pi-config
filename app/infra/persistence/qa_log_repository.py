# -*- coding: utf-8 -*-
"""
问答审计日志（MongoDB qa_logs 集合）。M3-01

需求锚点 2.9.8 单次问答审计记录：会话 ID、用户 ID、提问时间、提问文本、
鉴权通过列表、鉴权拦截列表、来源、消耗 Token 数与响应耗时。
消费方：审计查询接口（运营页）、FAQ 挖掘（M3-03）、缺口池、看板聚合。
"""
from datetime import datetime, timezone

from app.shared.clients.mongo_history_utils import get_history_mongo_tool


class QaLogRepository:

    def insert(self, entry: dict) -> str:
        doc = dict(entry)
        doc.setdefault("ts", datetime.now(timezone.utc))
        result = get_history_mongo_tool().db["qa_logs"].insert_one(doc)
        return str(result.inserted_id)

    def list_desc(self, limit: int = 50) -> list[dict]:
        cursor = (
            get_history_mongo_tool().db["qa_logs"]
            .find({}, {"_id": 0})
            .sort("ts", -1)
            .limit(limit)
        )
        return list(cursor)


qa_log_repository = QaLogRepository()
