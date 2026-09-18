#!/usr/bin/env python3
"""M4 闭环验证：TXT/DOCX 导入 → 默认拒绝 → admin 配 global → 用户可检索问答。"""
import sys, time, httpx

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
    c = httpx.Client(timeout=180)
    admin = {"Authorization": "Bearer " + c.post(f"{QUERY}/auth/login", json={"username": "admin", "password": "admin123"}).json()["data"]["access_token"]}
    zhang = {"Authorization": "Bearer " + c.post(f"{QUERY}/auth/login", json={"username": "zhangsan", "password": "zhang123"}).json()["data"]["access_token"]}

    units = c.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=10).json()["data"]
    target = next((u for u in units if u["title"] == "海外直邮保税仓清关指引" and u["format"] == "docx"), None)
    check("找到 docx 导入的知识单元", target is not None, str([(u['title'], u['format']) for u in units]))
    if not target:
        return
    kid = target["id"]

    # 未配置权限（默认拒绝）
    r = c.post(f"{QUERY}/query", json={"query": "海外直邮清关延误怎么办"}, headers=zhang)
    check("未配置权限时默认拒绝", r.json().get("denied_ids") and kid in r.json().get("denied_ids", []),
          str(r.json().get("denied_ids")))

    # admin 配置 global
    r = c.put(f"{QUERY}/admin/knowledge/{kid}/permissions",
              json={"global_": True, "department_ids": [], "role_ids": [], "user_ids": []},
              headers=admin, timeout=10)
    check("配置全局公开", r.status_code == 200)

    # 张三可检索命中
    r = c.post(f"{QUERY}/query", json={"query": "海外直邮清关延误怎么办"}, headers=zhang)
    body = r.json()
    check("配置后问答命中引用", body.get("source") == "rag" and kid in body.get("allowed_ids", [])
          and "清关" in body.get("answer", ""), f"{body.get('source')} {body.get('answer', '')[:80]}")

    print(f"\nPASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
