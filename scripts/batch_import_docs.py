#!/usr/bin/env python3
"""
批量导入 doc/ 下的全部文档（分批上传 + 轮询 + 跳过已入库 + 报告）。
运行：.venv/bin/python scripts/batch_import_docs.py [--dir doc] [--batch 3] [--grant-global]
日志：/tmp/batch_import.log（stdout 重定向）；报告：/tmp/batch_import_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

QUERY = "http://127.0.0.1:55001"
SUPPORTED = (".pdf", ".md", ".docx", ".doc", ".txt")


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="doc")
    ap.add_argument("--batch", type=int, default=3)
    ap.add_argument("--grant-global", action="store_true")
    args = ap.parse_args()

    c = httpx.Client(timeout=600)
    admin = {"Authorization": "Bearer " + c.post(f"{QUERY}/auth/login", json={"username": "admin", "password": "admin123"}).json()["data"]["access_token"]}

    files = sorted(p for p in Path(args.dir).iterdir() if p.suffix.lower() in SUPPORTED)
    existing = {u["title"] for u in c.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=30).json()["data"]}
    todo = [p for p in files if p.stem not in existing]
    log(f"待导入 {len(todo)} / 共 {len(files)} 个文件（已跳过已入库 {len(files) - len(todo)} 个）")

    report = {"total": len(todo), "success": [], "failed": []}
    t0 = time.time()

    for i in range(0, len(todo), args.batch):
        chunk = todo[i:i + args.batch]
        log(f"--- 批次 {i // args.batch + 1}：{len(chunk)} 个文件上传 ---")
        try:
            fs = [("files", (p.name, open(p, "rb"), "application/pdf" if p.suffix == ".pdf" else "application/octet-stream")) for p in chunk]
            r = c.post(f"{QUERY}/admin/import/upload", files=fs, data={"allowed_roles": '["admin","common_user"]'}, headers=admin)
            for _, (_, fh, _) in fs:
                fh.close()
            if r.status_code != 200:
                log(f"上传失败: {r.status_code} {r.text[:120]}")
                report["failed"] += [{"file": p.name, "reason": f"upload {r.status_code}"} for p in chunk]
                continue
            task_ids = r.json()["task_ids"]
        except Exception as exc:
            log(f"上传异常: {exc!r}")
            report["failed"] += [{"file": p.name, "reason": repr(exc)[:80]} for p in chunk]
            continue

        pending = {p.name: tid for p, tid in zip(chunk, task_ids)}
        deadline = time.time() + 3600  # 单批最长 1 小时
        while pending and time.time() < deadline:
            time.sleep(15)
            for name, tid in list(pending.items()):
                try:
                    st = c.get(f"{QUERY}/admin/import/status/{tid}", headers=admin, timeout=30).json()
                except Exception:
                    continue
                status = st.get("status")
                if status == "completed":
                    log(f"✓ {name}")
                    report["success"].append(name)
                    pending.pop(name)
                elif status == "failed":
                    log(f"✗ {name} 失败")
                    report["failed"].append({"file": name, "reason": "import failed"})
                    pending.pop(name)
        for name in pending:
            log(f"✗ {name} 超时未完成")
            report["failed"].append({"file": name, "reason": "timeout"})
        done = len(report["success"]) + len(report["failed"])
        log(f"进度 {done}/{len(todo)}（成功 {len(report['success'])}，失败 {len(report['failed'])}）")

    # 可选：为本次导入的知识单元配置全局公开
    if args.grant_global and report["success"]:
        units = c.get(f"{QUERY}/admin/knowledge", headers=admin, timeout=30).json()["data"]
        for u in units:
            if u["title"] in {Path(n).stem for n in report["success"]}:
                c.put(f"{QUERY}/admin/knowledge/{u['id']}/permissions",
                      json={"global_": True, "department_ids": [], "role_ids": [], "user_ids": []},
                      headers=admin, timeout=30)
        log("已为本次导入的知识单元配置「全局公开」")

    report["elapsedMin"] = round((time.time() - t0) / 60, 1)
    Path("/tmp/batch_import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"===== 结束：成功 {len(report['success'])} / 失败 {len(report['failed'])}，耗时 {report['elapsedMin']} 分钟 =====")


if __name__ == "__main__":
    main()
