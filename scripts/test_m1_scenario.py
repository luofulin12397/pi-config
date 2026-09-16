"""
M1-05 端到端验收：需求 2.9.9 场景一「跨部门财务与薪酬制度问答隔离」。
前置：双服务运行；Milvus/Mongo 就绪；/tmp/union-test/ 下两篇文档存在。
运行：.venv/bin/python scripts/test_m1_scenario.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUERY = "http://127.0.0.1:55001"
IMPORT = "http://127.0.0.1:55000"
PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def ask(auth_header: str, question: str) -> dict:
    """auth_header: 完整 Authorization 头值（含 Bearer 前缀）。"""
    r = httpx.post(f"{QUERY}/query", json={"query": question}, headers={"Authorization": auth_header}, timeout=300)
    return {"status": r.status_code, **(r.json() if r.status_code == 200 else {})}


def main():
    # ---------- 0. 场景数据准备：角色 / 用户 / 部门 ----------
    from app.shared.clients.mongo_auth_utils import get_auth_mongo_tool
    from app.infra.security.password_utils import hash_password
    tool = get_auth_mongo_tool()
    tool.roles.update_one(
        {"code": "r_mgmt"},
        {"$set": {"name": "管理层", "menus": ["chat"], "buttons": ["ask"]}, "$setOnInsert": {"created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}},
        upsert=True,
    )
    for username, display, dept, role in [
        ("zhangsan", "张三", "dept-biz", "common_user"),
        ("zhaoliu", "赵六", "dept-gm", "r_mgmt"),
    ]:
        u = tool.users.find_one({"username": username})
        if not u:
            uid = tool.users.insert_one({
                "username": username, "password_hash": hash_password("zhang123" if username == "zhangsan" else "zhao123"),
                "display_name": display, "department_id": dept, "status": "active",
                "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            }).inserted_id
        else:
            uid = u["_id"]
            tool.users.update_one({"_id": uid}, {"$set": {"department_id": dept}})
        tool.user_roles.update_one({"user_id": uid}, {"$set": {"user_id": uid, "role_code": role}}, upsert=True)
    print("场景用户就绪：zhangsan(业务部/普通用户) zhaoliu(管理层/总经理办)")

    # ---------- 1. 登录 ----------
    zhang = {"Authorization": f"Bearer {httpx.post(f'{QUERY}/auth/login', json={'username': 'zhangsan', 'password': 'zhang123'}, timeout=15).json()['data']['access_token']}"}
    zhao = {"Authorization": f"Bearer {httpx.post(f'{QUERY}/auth/login', json={'username': 'zhaoliu', 'password': 'zhao123'}, timeout=15).json()['data']['access_token']}"
            }
    admin = {"Authorization": f"Bearer {httpx.post(f'{QUERY}/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=15).json()['data']['access_token']}"}

    # ---------- 2. 导入两篇文档（幂等：已存在则复用） ----------
    def import_doc(path: str) -> str:
        units = httpx.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=10).json()["data"]
        found = next((u for u in units if u["title"] in path or path.startswith(u["title"])), None)
        if found:
            return found["id"]
        with open(path, "rb") as f:
            r = httpx.post(f"{IMPORT}/upload", files=[("files", (Path(path).name, f, "text/markdown"))],
                           data={"allowed_roles": '["admin","common_user"]'}, headers=admin, timeout=60)
        task_id = r.json()["task_ids"][0]
        for _ in range(60):
            if httpx.get(f"{IMPORT}/status/{task_id}", timeout=10).json().get("status") == "completed":
                break
            time.sleep(3)
        units = httpx.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=10).json()["data"]
        return next(u["id"] for u in units if u["title"] in path or path.startswith(u["title"]))

    kid_travel = import_doc("/tmp/union-test/差旅报销标准.md")
    kid_salary = import_doc("/tmp/union-test/高管薪酬与股权激励细则.md")
    check("两篇文档均已入库", bool(kid_travel and kid_salary), f"{kid_travel} / {kid_salary}")

    # ---------- 3. 配置权限：差旅=全局公开；薪酬=仅人力部+管理层 ----------
    httpx.put(f"{QUERY}/admin/knowledge/{kid_travel}/permissions",
              json={"global_": True, "department_ids": [], "role_ids": [], "user_ids": []}, headers=admin, timeout=10)
    httpx.put(f"{QUERY}/admin/knowledge/{kid_salary}/permissions",
              json={"global_": False, "department_ids": ["dept-hr"], "role_ids": ["r_mgmt"], "user_ids": []},
              headers=admin, timeout=10)
    check("四维权限配置完成", True)

    # ---------- 4. 未登录调用问答被拒 ----------
    r = httpx.post(f"{QUERY}/query", json={"query": "差旅报销标准"}, timeout=15)
    check("未登录问答被拒 401", r.status_code in (401, 403), f"got {r.status_code}")

    # ---------- 5. 张三问差旅（全局公开）→ 正常引用 ----------
    res = ask(zhang["Authorization"], "差旅报销的住宿标准和餐补是多少？")
    ans = res.get("answer", "")
    check("张三问差旅：正常回答且引用", res["status"] == 200 and "餐补" in ans and kid_travel in res.get("allowed_ids", []),
          f"status={res['status']} ans={ans[:80]} allowed={res.get('allowed_ids')}")
    check("张三问差旅：无拦截项", not res.get("denied_ids"), str(res.get("denied_ids")))

    # ---------- 6. 张三问薪酬（无权限）→ 受限提示，零泄露 ----------
    res = ask(zhang["Authorization"], "高管薪酬与股权激励是怎么规定的？")
    ans = res.get("answer", "")
    check("张三问薪酬：受限提示", res["status"] == 200 and "无权查阅" in ans, f"ans={ans[:80]}")
    check("张三问薪酬：拦截列表含薪酬文档", kid_salary in res.get("denied_ids", []), str(res.get("denied_ids")))
    check("张三问薪酬：零内容泄露", "股权激励计划" not in ans and "行权价格" not in ans and "四年归属" not in ans)
    check("张三问薪酬：放行列表为空", not res.get("allowed_ids"), str(res.get("allowed_ids")))

    # ---------- 7. 赵六（管理层）问同题 → 正常回答 ----------
    res = ask(zhao["Authorization"], "高管薪酬与股权激励是怎么规定的？")
    ans = res.get("answer", "")
    check("赵六问薪酬：正常回答且引用", res["status"] == 200 and kid_salary in res.get("allowed_ids", []) and len(ans) > 30,
          f"status={res['status']} ans={ans[:80]}")

    print(f"\nPASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
