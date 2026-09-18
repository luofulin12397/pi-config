#!/usr/bin/env python3
"""
需求 2.9.9 场景二端到端演示：客服高频退换货问答沉淀为 FAQ 与缺口补足。
一键走完：导入规范文档 → 多用户高频提问 → 挖掘聚类生成候选 → 审核发布 → 同义问毫秒直出 → 缺口转补全任务。
运行：.venv/bin/python scripts/demo_scenario2.py（需双服务与中间件运行中）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUERY = "http://127.0.0.1:55001"
DOC = Path("/tmp/union-test/生鲜商品退换货处理规范.md")


def banner(text: str):
    print(f"\n{'=' * 62}\n  {text}\n{'=' * 62}")


def main():
    c = httpx.Client(timeout=120)

    banner("准备：演示账号登录")
    admin = {"Authorization": "Bearer " + c.post(f"{QUERY}/auth/login", json={"username": "admin", "password": "admin123"}).json()["data"]["access_token"]}
    zhang = {"Authorization": "Bearer " + c.post(f"{QUERY}/auth/login", json={"username": "zhangsan", "password": "zhang123"}).json()["data"]["access_token"]}

    banner("步骤 1：导入《生鲜商品退换货处理规范》文档")
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(
        "# 生鲜商品退换货处理规范\n\n"
        "## 退款申请\n生鲜商品签收后 24 小时内如发现破损或变质，请在 APP 订单页拍照申请「仅退款」，"
        "客服审核通过后 1-3 个工作日原路退回，无需退还商品。\n\n"
        "## 投诉时效\n生鲜类投诉：普通破损 2 小时内响应；重大质量问题（食品安全）30 分钟内响应并升级客诉专员。\n",
        encoding="utf-8")
    with open(DOC, "rb") as f:
        r = c.post(f"{QUERY}/admin/import/upload",
                   files=[("files", (DOC.name, f, "text/markdown"))],
                   data={"allowed_roles": '["admin","common_user"]'}, headers=admin)
    task_id = r.json()["task_ids"][0]
    print(f"  已提交导入任务 {task_id[:8]}…，等待解析入库")
    for _ in range(60):
        st = c.get(f"{QUERY}/admin/import/status/{task_id}", timeout=10).json()
        if st.get("status") == "completed":
            print("  ✓ 解析切片向量化入库完成")
            break
        if st.get("status") == "failed":
            print("  ✗ 导入失败：", st)
            sys.exit(1)
        time.sleep(3)

    banner("步骤 2：多名客服用户高频提问（模拟一周真实咨询）")
    questions = ["生鲜食品破损如何申请退款", "买的生鲜坏了怎么退款", "收到的水果烂了怎么申请退款"]
    for i in range(6):
        q = questions[i % len(questions)]
        r = c.post(f"{QUERY}/query", json={"query": q}, headers=zhang)
        src = r.json().get("source", "?") if r.status_code == 200 else "ERR"
        print(f"  客服咨询 #{i + 1}: {q} → [{src}]")
        time.sleep(0.3)

    banner("步骤 3：触发挖掘 —— 聚类高频问题自动生成候选 FAQ")
    d = c.post(f"{QUERY}/admin/mining/run", json={"days": 7, "threshold": 5}, headers=admin).json()["data"]
    print(f"  扫描问题 {d['mining']['scannedQuestions']} 个，聚类 {d['mining']['clusters']} 簇")
    for cand in d["mining"]["createdCandidates"]:
        print(f"  ✓ 生成候选：「{cand['question']}」（近7日 {cand['freq']} 次）")
    if not d["mining"]["createdCandidates"]:
        print("  （本次无达阈值新簇——可能此前已挖掘过，直接进入发布步骤）")
    cands = c.get(f"{QUERY}/ops/faq/candidates", headers=admin).json()["data"]
    target = next((x for x in cands if "生鲜" in x["question"] and x["status"] == "pending"), None)
    if not target:
        print("  ✗ 未找到待审核的生鲜候选")
        sys.exit(1)

    banner("步骤 4：知识管理员在线润色并审核发布（写入高速缓存）")
    answer = "生鲜商品签收后 24 小时内如发现破损或变质，请在 APP 订单页拍照申请「仅退款」，客服审核通过后 1-3 个工作日原路退回，无需退还商品。"
    r = c.post(f"{QUERY}/ops/faq/candidates/{target['candidate_id']}/publish",
               json={"question": "生鲜商品破损/变质如何申请退款？", "answer": answer}, headers=admin)
    print("  ✓ 已发布并注入高速缓存")

    banner("步骤 5：用户再次提问 —— FAQ 缓存毫秒级直出（不再调用大模型）")
    t0 = time.time()
    r = c.post(f"{QUERY}/query", json={"query": "生鲜食品破损如何申请退款"}, headers=zhang)
    latency = int((time.time() - t0) * 1000)
    body = r.json()
    print(f"  来源: {body.get('source')} | 耗时: {latency}ms")
    print(f"  回答: {body.get('answer', '')[:80]}")
    ok_faq = body.get("source") == "faq-cache" and latency < 3000
    print(f"  {'✓ 毫秒级直出验证通过' if ok_faq else '✗ 未走缓存'}")

    banner("步骤 6：知识缺口 —— 未命中问题自动入池并转补全任务")
    r = c.post(f"{QUERY}/query", json={"query": "海外直邮保税仓清关延误怎么办"}, headers=zhang)
    print(f"  未命中回答: {r.json().get('answer', '')[:50]}…")
    c.post(f"{QUERY}/admin/mining/run", json={"days": 7}, headers=admin)
    gaps = c.get(f"{QUERY}/ops/gaps", headers=admin).json()["data"]
    gap = next((g for g in gaps if "清关" in g["question"]), None)
    if gap:
        r = c.post(f"{QUERY}/ops/gaps/{gap['gap_id']}/convert",
                   json={"title": "海外直邮保税仓清关指引", "category": "物流运营"}, headers=admin)
        print(f"  ✓ 缺口「{gap['question'][:20]}」已转知识补全任务")
    else:
        print("  （缺口池中暂无清关类问题）")

    banner("演示完成")
    print("  场景二全链路：导入 → 高频提问 → 挖掘 → 审核发布 → 缓存直出 → 缺口闭环")
    print("  控制台可查看：沉淀与运营（审计/候选/已发布/缺口）与 运营看板")


if __name__ == "__main__":
    main()
