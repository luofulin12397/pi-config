#!/usr/bin/env python3
"""M3-01/02 端到端验收（审计落库 + FAQ 缓存直出）。运行：.venv/bin/python scripts/test_m3_sediment.py"""
import sys, time, httpx

sys.path.insert(0, "/root/project/RAG智库管理平台/ai_rag_knowbase-master")
from app.shared.clients.mongo_qa_cache_utils import _get_qa_cache_collection  # noqa: E402

QUERY = "http://127.0.0.1:55001"
PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def main():
    _get_qa_cache_collection().delete_many({})
    c = httpx.Client(timeout=120)
    admin = {"Authorization": "Bearer " + c.post(f"{QUERY}/auth/login", json={"username": "admin", "password": "admin123"}).json()["data"]["access_token"]}
    zhang = {"Authorization": "Bearer " + c.post(f"{QUERY}/auth/login", json={"username": "zhangsan", "password": "zhang123"}).json()["data"]["access_token"]}

    # 0. 恢复差旅文档全局公开（此前验收脚本清空过其权限）
    units = c.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=10).json()["data"]
    travel = next((u for u in units if "差旅" in u["title"]), None)
    if travel:
        c.put(f"{QUERY}/admin/knowledge/{travel['id']}/permissions",
              json={"global_": True, "department_ids": [], "role_ids": [], "user_ids": []},
              headers=admin, timeout=10)
    check("差旅文档恢复全局公开", bool(travel))

    # 1. 普通 RAG 问答
    r = c.post(f"{QUERY}/query", json={"query": "差旅报销的住宿标准和餐补是多少？"}, headers=zhang)
    check("普通 RAG 问答正常", r.status_code == 200 and r.json().get("source") == "rag" and "餐补" in r.json().get("answer", ""),
          f"source={r.json().get('source')}")

    # 2. 添加候选 → 发布
    r = c.post(f"{QUERY}/ops/faq/candidates", json={
        "question": "生鲜商品破损/变质如何申请退款？",
        "answer": "生鲜商品签收后 24 小时内如发现破损或变质，请在 APP 订单页拍照申请「仅退款」，客服审核通过后 1-3 个工作日原路退回，无需退还商品。",
    }, headers=admin)
    check("手动添加候选", r.status_code == 200, r.text[:100])
    cid = r.json()["data"]["candidate_id"]
    r = c.post(f"{QUERY}/ops/faq/candidates/{cid}/publish", json={
        "question": "生鲜商品破损/变质如何申请退款？",
        "answer": "生鲜商品签收后 24 小时内如发现破损或变质，请在 APP 订单页拍照申请「仅退款」，客服审核通过后 1-3 个工作日原路退回，无需退还商品。",
    }, headers=admin)
    check("审核发布成功且入缓存", r.status_code == 200 and r.json()["data"]["cacheEnabled"])

    # 3. 同义问句 → FAQ 直出
    t0 = time.time()
    r = c.post(f"{QUERY}/query", json={"query": "买的生鲜坏了怎么退款"}, headers=zhang)
    latency = int((time.time() - t0) * 1000)
    body = r.json()
    check("同义问句命中 FAQ 直出", body.get("source") == "faq-cache" and "仅退款" in body.get("answer", ""),
          f"source={body.get('source')}")
    check("毫秒级响应(<3s)", latency < 3000, f"{latency}ms")

    # 4. hitCount 与审计
    faqs = c.get(f"{QUERY}/ops/faqs", headers=admin).json()["data"]
    target = next((f for f in faqs if "生鲜" in f["question"]), None)
    check("hitCount=1", target and target.get("hitCount") == 1)
    logs = c.get(f"{QUERY}/ops/audit/logs?limit=10", headers=admin).json()["data"]
    check("审计覆盖 rag + faq-cache", any(l.get("source") == "faq-cache" for l in logs) and any(l.get("source") == "rag" for l in logs))

    print(f"\nPASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
