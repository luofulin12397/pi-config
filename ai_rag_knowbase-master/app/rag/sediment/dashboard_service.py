# -*- coding: utf-8 -*-
"""
运营看板聚合服务（M3-04）。数据源：qa_logs 审计日志 + knowledge_units 台账。

契约 docs/api-contract.md §6。单端点 overview 一次返回全部指标（前端一次拉取）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.infra.persistence.knowledge_repository import knowledge_repository
from app.infra.persistence.qa_log_repository import qa_log_repository


def _to_dt(ts):
    # pymongo 读回的 datetime 为 naive UTC，统一补时区避免比较异常
    dt = ts if isinstance(ts, datetime) else datetime.fromtimestamp(
        float(ts) / 1000 if float(ts) > 1e11 else float(ts), tz=timezone.utc)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _day_start(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def overview(days: int = 7) -> dict:
    now = datetime.now(timezone.utc)
    today0 = _day_start(now)
    since = today0 - timedelta(days=days - 1)
    all_logs = [l for l in qa_log_repository.list_desc(limit=5000) if _to_dt(l.get("ts")) >= since]
    today_logs = [l for l in all_logs if _to_dt(l["ts"]) >= today0]
    rag_today = [l for l in today_logs if l.get("source") == "rag"]

    pv = len(today_logs)
    uv = len({l.get("user_id") for l in today_logs if l.get("user_id")})
    faq_hits = len([l for l in today_logs if l.get("source") == "faq-cache"])
    token_today = sum(int(l.get("tokens") or 0) for l in today_logs)
    avg_latency = (sum(int(l.get("latency") or 0) for l in rag_today) // len(rag_today)) if rag_today else 0
    kb_total = len([u for u in knowledge_repository.list_units(limit=1000) if u.get("enabled")])

    # 按天趋势
    days_list, day_tokens, day_pv = [], [], []
    for i in range(days):
        start = since + timedelta(days=i)
        end = start + timedelta(days=1)
        ls = [l for l in all_logs if start <= _to_dt(l["ts"]) < end]
        days_list.append(f"{start.month}/{start.day}")
        day_tokens.append(sum(int(l.get("tokens") or 0) for l in ls))
        day_pv.append(len(ls))

    # 高频问题 TOP5（近 N 日，按原文聚合——真实聚类见挖掘服务）
    q_counter: dict[str, int] = {}
    for l in all_logs:
        q = (l.get("question") or "").strip()
        if q:
            q_counter[q] = q_counter.get(q, 0) + 1
    top_questions = sorted(q_counter.items(), key=lambda x: -x[1])[:5]

    # 热门知识 TOP5（放行引用计数）
    k_counter: dict[str, int] = {}
    for l in all_logs:
        for kid in l.get("allowed_ids", []):
            k_counter[kid] = k_counter.get(kid, 0) + 1
    top_knowledge = sorted(k_counter.items(), key=lambda x: -x[1])[:5]

    # 延时分布（RAG 来源，5 桶）
    buckets = [(0, 1000, "<1s"), (1000, 2000, "1-2s"), (2000, 3000, "2-3s"), (3000, 5000, "3-5s"), (5000, 10 ** 9, ">5s")]
    latency_dist = [
        {"label": label, "n": len([l for l in all_logs if l.get("source") == "rag" and b0 <= int(l.get("latency") or 0) < b1])}
        for b0, b1, label in buckets
    ]

    return {
        "pv": pv, "uv": uv, "kbTotal": kb_total,
        "faqHitRate": round(faq_hits / pv * 100) if pv else 0,
        "tokenToday": token_today, "avgLatency": avg_latency,
        "trend": {"days": days_list, "tokens": day_tokens, "pv": day_pv},
        "topQuestions": [{"q": q, "n": n} for q, n in top_questions],
        "topKnowledge": [{"kid": kid, "n": n} for kid, n in top_knowledge],
        "latencyDist": latency_dist,
    }
