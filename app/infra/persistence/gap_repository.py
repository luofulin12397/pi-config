# -*- coding: utf-8 -*-
"""
知识缺口池（MongoDB knowledge_gaps 集合）。M3-03

需求锚点 2.9.4：检索相似度低于置信度阈值或未命中的提问自动归入缺口池，
结合提问频次聚合生成知识建设需求，闭环指导知识管理员补充文档。

产生：mining_service.sync_gaps 从 qa_logs 的 no-result 记录聚合（相似问题合并频次）。
闭环：管理员「转知识补全任务」→ 创建停用占位知识单元（补充内容后启用）→ gap 置 converted。
"""
from datetime import datetime, timezone

from app.shared.clients.mongo_history_utils import get_history_mongo_tool


def _now():
    return datetime.now(timezone.utc)


def _col():
    return get_history_mongo_tool().db["knowledge_gaps"]


class GapRepository:

    def upsert_hit(self, *, question: str, user_department: str = "") -> dict:
        """相似问题命中缺口池：频次 +1 / 新建。相似判定用原文精确匹配 + 前缀归一（挖掘侧已做相似合并）。"""
        col = _col()
        exist = col.find_one({"question": question, "status": "open"})
        if exist:
            col.update_one({"_id": exist["_id"]}, {"$inc": {"freq": 1}, "$set": {"lastAt": _now()}})
            exist["freq"] += 1
            return exist
        doc = {
            "gap_id": "g" + str(int(_now().timestamp() * 1000)),
            "question": question, "department": user_department,
            "freq": 1, "status": "open", "createdAt": _now(), "lastAt": _now(),
        }
        col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    def list_open(self) -> list[dict]:
        return list(_col().find({"status": "open"}, {"_id": 0}).sort("freq", -1))

    def get(self, gap_id: str) -> dict | None:
        return _col().find_one({"gap_id": gap_id}, {"_id": 0})

    def convert(self, gap_id: str, knowledge_id: str) -> int:
        return _col().update_one(
            {"gap_id": gap_id},
            {"$set": {"status": "converted", "convertedKnowledgeId": knowledge_id, "convertedAt": _now()}}
        ).modified_count


gap_repository = GapRepository()
