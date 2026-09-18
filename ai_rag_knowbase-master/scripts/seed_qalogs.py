#!/usr/bin/env python3
"""注入近 7 天演示问答日志（让挖掘/缺口/看板有数据可展示）。
运行：.venv/bin/python scripts/seed_qalogs.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.shared.clients.mongo_auth_utils import get_auth_mongo_tool  # noqa: E402
from app.shared.clients.mongo_history_utils import get_history_mongo_tool  # noqa: E402

random.seed(42)
NOW = datetime.now(timezone.utc)
tool = get_auth_mongo_tool()

# 用户映射
users = {u["username"]: str(u["_id"]) for u in tool.users.find({}, {"username": 1})}
U = {"zhangsan": users["zhangsan"], "zhaoliu": users["zhaoliu"], "admin": users["admin"]}

# 知识单元 kid 映射（用于 allowed_ids）
kids = {u["title"]: u["knowledge_id"] for u in tool.db["knowledge_units"].find({}, {"title": 1, "knowledge_id": 1})}
K_TRAVEL = kids.get("差旅报销标准", "")
K_SALARY = kids.get("高管薪酬与股权激励细则", "")

FRESH_Q = ["生鲜食品破损如何申请退款", "买的生鲜坏了怎么退款", "收到的水果烂了怎么申请退款",
           "生鲜破损退款流程", "生鲜变质怎么赔偿"]
TRAVEL_Q = ["差旅报销的住宿标准和餐补是多少？", "出差住宿报销上限是多少", "差旅餐补怎么算"]
SALARY_Q = "高管薪酬与股权激励是怎么规定的？"
GAP_Q = ["海外直邮保税仓清关延误怎么办", "海外订单清关卡住了怎么处理", "保税仓清关延误有赔偿吗",
         "海外直邮的包裹清关要多久"]

logs = []
for d in range(6, -1, -1):
    day0 = (NOW - timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
    def ts():
        return day0 + timedelta(seconds=random.randint(0, 86399))
    # 普通问答（差旅公开知识）
    for _ in range(random.randint(3, 6)):
        logs.append(dict(user_id=U["zhangsan"], question=random.choice(TRAVEL_Q), source="rag",
                         allowed_ids=[K_TRAVEL], denied_ids=[], tokens=random.randint(200, 800),
                         latency=random.randint(2000, 5000), ts=ts()))
    # 薪酬越权尝试（张三）→ denied
    for _ in range(random.randint(0, 2)):
        logs.append(dict(user_id=U["zhangsan"], question=SALARY_Q, source="denied",
                         allowed_ids=[], denied_ids=[K_SALARY], tokens=random.randint(80, 150),
                         latency=random.randint(1500, 3000), ts=ts()))
    # 赵六问薪酬 → 正常
    if random.random() < 0.6:
        logs.append(dict(user_id=U["zhaoliu"], question=SALARY_Q, source="rag",
                         allowed_ids=[K_SALARY], denied_ids=[], tokens=random.randint(300, 700),
                         latency=random.randint(2000, 4000), ts=ts()))
    # 生鲜退换货高频（挖掘目标：7 天合计 ≥10）
    for _ in range(random.randint(1, 3)):
        logs.append(dict(user_id=U["zhaoliu"], question=random.choice(FRESH_Q), source="rag",
                         allowed_ids=[K_SALARY] if False else [], denied_ids=[],
                         tokens=random.randint(200, 500), latency=random.randint(1800, 3500), ts=ts()))
    # 未命中（缺口）
    if random.random() < 0.8:
        logs.append(dict(user_id=U["zhangsan"], question=random.choice(GAP_Q), source="no-result",
                         allowed_ids=[], denied_ids=[], tokens=random.randint(50, 120),
                         latency=random.randint(800, 1500), ts=ts()))

# 清旧演示数据（保留真实联调产生的少量记录也无妨——统一清空保证统计干净）
get_history_mongo_tool().db["qa_logs"].delete_many({"demo": True})
for l in logs:
    l["demo"] = True
    l["session_id"] = "demo-" + str(random.randint(1000, 9999))
get_history_mongo_tool().db["qa_logs"].insert_many(logs)
print(f"已注入 {len(logs)} 条演示审计日志（近 7 天）")
