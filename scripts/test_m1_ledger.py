"""
M1-02 知识单元台账 集成验收脚本（需 Mongo + Milvus + 双服务运行）。
前置：python3 scripts/seed_auth.py 已执行；联调用户已建（见 build_integration_users）。
运行：.venv/bin/python scripts/test_m1_ledger.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

IMPORT = "http://127.0.0.1:55000"
QUERY = "http://127.0.0.1:55001"
DOC = Path("/tmp/union-test/差旅报销标准.md")

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def main():
    # 0. 登录（admin）
    r = httpx.post(f"{QUERY}/auth/login", json={"username": "admin", "password": "admin123"}, timeout=15)
    check("admin 登录", r.status_code == 200, r.text[:120])
    token = r.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. 上传 MD → 轮询导入任务完成
    with open(DOC, "rb") as f:
        r = httpx.post(f"{IMPORT}/upload", files=[("files", (DOC.name, f, "text/markdown"))],
                       data={"allowed_roles": '["admin","common_user"]'}, headers=headers, timeout=60)
    check("上传《差旅报销标准.md》", r.status_code == 200, r.text[:200])
    task_id = r.json()["task_ids"][0]
    for _ in range(60):
        st = httpx.get(f"{IMPORT}/status/{task_id}", timeout=10).json()
        status = str(st.get("status", ""))
        if status.lower() in ("completed",):
            break
        if status.lower() in ("failed",):
            check("导入任务完成", False, str(st)[:200])
            return
        time.sleep(3)
    check("导入任务完成", True)

    # 2. 台账出现该知识单元
    units = httpx.get(f"{QUERY}/admin/knowledge", headers=headers, timeout=10).json()["data"]
    stem = DOC.stem
    target = next((u for u in units if u["fileTitle"] in (DOC.name, stem) or u["title"] == stem), None)
    check("台账出现《差旅报销标准》", target is not None, str(units)[:200])
    if not target:
        return
    kid = target["id"]

    # 3. 停用 → 检索不命中
    r = httpx.put(f"{QUERY}/admin/knowledge/{kid}", json={"enabled": False}, headers=headers, timeout=10)
    check("停用接口生效", r.status_code == 200 and r.json()["data"]["enabled"] is False, r.text[:150])
    r = httpx.post(f"{QUERY}/query", json={"query": "差旅报销的住宿标准和餐补是多少？"},
                   headers=headers, timeout=180)
    answer_disabled = str(r.json().get("answer", "")) if r.status_code == 200 else ""
    check("停用后问答不引用其内容", "500" not in answer_disabled and "餐补" not in answer_disabled,
          answer_disabled[:150])

    # 4. 重新启用 → 检索命中
    httpx.put(f"{QUERY}/admin/knowledge/{kid}", json={"enabled": True}, headers=headers, timeout=10)
    r = httpx.post(f"{QUERY}/query", json={"query": "差旅报销的住宿标准和餐补是多少？"},
                   headers=headers, timeout=180)
    answer_enabled = str(r.json().get("answer", "")) if r.status_code == 200 else ""
    check("启用后问答正常引用", ("500" in answer_enabled) or ("餐补" in answer_enabled), answer_enabled[:150])

    # 5. 删除 → 台账消失且不再命中
    r = httpx.delete(f"{QUERY}/admin/knowledge/{kid}", headers=headers, timeout=30)
    check("删除接口生效", r.status_code == 200, r.text[:150])
    units = httpx.get(f"{QUERY}/admin/knowledge", headers=headers, timeout=10).json()["data"]
    check("删除后台账消失", all(u["id"] != kid for u in units))

    print(f"\nPASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
