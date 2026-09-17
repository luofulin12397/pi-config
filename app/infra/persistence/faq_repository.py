# -*- coding: utf-8 -*-
"""
FAQ 沉淀仓储（MongoDB faqs 已发布库 + faq_candidates 候选池）。M3-02

- 已发布且 cacheEnabled 的 FAQ 参与问答管线优先匹配（node_query_cache 最前）
- 命中判定：问题向量与 FAQ question 向量的余弦相似度 ≥ FAQ_SIM_THRESHOLD
- 候选来源：手动添加（本票）+ qa_logs 聚类挖掘（M3-03）
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.shared.clients.mongo_history_utils import get_history_mongo_tool
from app.shared.model.embedding_utils import generate_embeddings

FAQ_SIM_THRESHOLD = 0.85  # 命中阈值（bge-m3 同义问句相似度高；调参留 settings 后续票）


def _now():
    return datetime.now(timezone.utc)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _dense(text: str) -> list[float]:
    return generate_embeddings([text])["dense"][0]


class FaqRepository:

    # ---------- 已发布库 ----------

    def list_published(self) -> list[dict]:
        return list(get_history_mongo_tool().db["faqs"]
                    .find({}, {"_id": 0, "question_dense": 0})
                    .sort("publishedAt", -1))

    def get_published(self, faq_id: str) -> dict | None:
        return get_history_mongo_tool().db["faqs"].find_one({"faq_id": faq_id}, {"_id": 0})

    def delete_published(self, faq_id: str) -> int:
        return get_history_mongo_tool().db["faqs"].delete_one({"faq_id": faq_id}).deleted_count

    def toggle_cache(self, faq_id: str, enabled: bool) -> int:
        return get_history_mongo_tool().db["faqs"].update_one(
            {"faq_id": faq_id}, {"$set": {"cacheEnabled": enabled}}
        ).modified_count

    def record_hit(self, faq_id: str) -> None:
        get_history_mongo_tool().db["faqs"].update_one(
            {"faq_id": faq_id}, {"$inc": {"hitCount": 1}}
        )

    # ---------- 候选池 ----------

    def list_candidates(self) -> list[dict]:
        return list(get_history_mongo_tool().db["faq_candidates"]
                    .find({}, {"_id": 0})
                    .sort("createdAt", -1))

    def add_candidate(self, *, question: str, answer: str = "", freq: int = 1, source: str = "manual") -> str:
        cid = "fc" + str(int(_now().timestamp() * 1000))
        get_history_mongo_tool().db["faq_candidates"].insert_one({
            "candidate_id": cid, "question": question, "answer": answer,
            "freq": freq, "source": source, "status": "pending",
            "createdAt": _now(),
        })
        return cid

    def get_candidate(self, candidate_id: str) -> dict | None:
        return get_history_mongo_tool().db["faq_candidates"].find_one(
            {"candidate_id": candidate_id}, {"_id": 0}
        )

    def reject_candidate(self, candidate_id: str) -> int:
        return get_history_mongo_tool().db["faq_candidates"].update_one(
            {"candidate_id": candidate_id}, {"$set": {"status": "rejected"}}
        ).modified_count

    # ---------- 发布（候选 → 已发布，含 question 向量预计算） ----------

    def publish(self, *, candidate_id: str, question: str, answer: str) -> str:
        fid = "f" + str(int(_now().timestamp() * 1000))
        cand = self.get_candidate(candidate_id)
        get_history_mongo_tool().db["faqs"].insert_one({
            "faq_id": fid, "question": question, "answer": answer,
            "question_dense": _dense(question),
            "cacheEnabled": True, "hitCount": 0,
            "confidence": (cand or {}).get("confidence"),
            "freq": (cand or {}).get("freq"),
            "publishedAt": _now(),
        })
        get_history_mongo_tool().db["faq_candidates"].update_one(
            {"candidate_id": candidate_id}, {"$set": {"status": "published"}}
        )
        return fid

    # ---------- 问答管线匹配 ----------

    def match(self, question: str) -> dict | None:
        """返回命中的已发布 FAQ（含 sim/faq_id/question/answer），未命中返回 None。"""
        docs = list(get_history_mongo_tool().db["faqs"].find({"cacheEnabled": True}))
        if not docs:
            return None
        q_dense = _dense(question)
        best = None
        for d in docs:
            sim = _cosine(q_dense, d.get("question_dense") or [])
            if best is None or sim > best["sim"]:
                best = dict(d, sim=sim)
        if best and best["sim"] >= FAQ_SIM_THRESHOLD:
            return {"faq_id": best["faq_id"], "question": best["question"],
                    "answer": best["answer"], "sim": best["sim"]}
        return None


faq_repository = FaqRepository()
