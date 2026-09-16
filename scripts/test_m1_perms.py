"""
M1-03 四维权限配置接口 集成验收。
前置：双服务运行；admin（全量按钮）；tester（仅 ask，无 perm 按钮）；台账中存在知识单元。
运行：.venv/bin/python scripts/test_m1_perms.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUERY = "http://127.0.0.1:55001"
PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def login(username: str, password: str) -> str:
    r = httpx.post(f"{QUERY}/auth/login", json={"username": username, "password": password}, timeout=15)
    return r.json()["data"]["access_token"]


def main():
    admin = {"Authorization": f"Bearer {login('admin', 'admin123')}"}
    tester = {"Authorization": f"Bearer {login('tester', 'test123')}"}

    # 前置：确保台账中有一个知识单元（为空则自动上传导入一篇 MD）
    units = httpx.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=10).json()["data"]
    if not units:
        doc = Path("/tmp/union-test/差旅报销标准.md")
        with open(doc, "rb") as f:
            r = httpx.post("http://127.0.0.1:55000/upload",
                           files=[("files", (doc.name, f, "text/markdown"))],
                           data={"allowed_roles": '["admin","common_user"]'},
                           headers=admin, timeout=60)
        task_id = r.json()["task_ids"][0]
        for _ in range(60):
            status = httpx.get(f"http://127.0.0.1:55000/status/{task_id}", timeout=10).json().get("status", "")
            if status == "completed":
                break
            if status == "failed":
                print("前置导入失败")
                sys.exit(2)
            time.sleep(3)
        units = httpx.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=10).json()["data"]
        check("前置导入后台账出现知识单元", bool(units))
    kid = units[0]["id"]

    four_dims = {"global_": False, "department_ids": ["dept-hr"], "role_ids": ["r_mgmt"], "user_ids": ["u-01"]}

    # 1. 无 perm 按钮的角色调用被拒
    r = httpx.put(f"{QUERY}/admin/knowledge/{kid}/permissions", json=four_dims, headers=tester, timeout=10)
    check("无 perm 按钮角色被拒 403", r.status_code == 403, f"got {r.status_code}")

    # 2. admin 配置四维 → 回显一致
    r = httpx.put(f"{QUERY}/admin/knowledge/{kid}/permissions", json=four_dims, headers=admin, timeout=10)
    check("四维权限保存成功", r.status_code == 200, r.text[:150])
    saved = r.json()["data"]["perms"]
    check("保存回显一致", saved == {"global": False, "department_ids": ["dept-hr"], "role_ids": ["r_mgmt"], "user_ids": ["u-01"]}, str(saved))

    # 3. 台账权限标签
    units = httpx.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=10).json()["data"]
    target = next((u for u in units if u["id"] == kid), {})
    check("台账含权限标签", "部门×1" in target.get("permLabels", []) or any("部门" in x for x in target.get("permLabels", [])),
          str(target.get("permLabels")))

    # 4. 缓存失效：配置变更后 cacheInvalidated 字段出现（有缓存时 >0，无缓存时 0 均可接受）
    r = httpx.put(f"{QUERY}/admin/knowledge/{kid}/permissions", json={"global_": True}, headers=admin, timeout=10)
    check("权限变更触发缓存清理机制", "cacheInvalidated" in r.json().get("data", {}), r.text[:150])

    # 5. 全部清空 → 默认拒绝（需求 2.9.4）
    r = httpx.put(f"{QUERY}/admin/knowledge/{kid}/permissions",
                  json={"global_": False, "department_ids": [], "role_ids": [], "user_ids": []},
                  headers=admin, timeout=10)
    perms = r.json()["data"]["perms"]
    from app.infra.security.perm_engine import has_access
    check("清空后默认拒绝", not has_access({"user_id": "u-any", "department_id": "d-any", "role_ids": ["r-any"]}, perms))

    print(f"\nPASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
