#!/usr/bin/env python3
"""一键启动 Import + Query 双服务（默认 :8000 / :8001），使用 uv run。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_settings():
    os.chdir(PROJECT_ROOT)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from app.shared.config.settings_config import settings

    return settings


def _browser_host(bind_host: str) -> str:
    if bind_host in ("0.0.0.0", "", "::"):
        return "127.0.0.1"
    return bind_host


def _uvicorn_cmd(app: str, host: str, port: int) -> list[str]:
    return [
        "uv",
        "run",
        "uvicorn",
        app,
        "--host",
        host,
        "--port",
        str(port),
    ]


def _start_process(name: str, cmd: list[str]) -> subprocess.Popen:
    print(f"[启动] {name}")
    print(f"       {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=PROJECT_ROOT)


def _stop_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    for name, proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for name, proc in processes:
        if proc.poll() is not None:
            continue
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            print(f"[强制] {name} 未响应，正在 kill")
            proc.kill()
            proc.wait(timeout=3)


def main() -> int:
    if shutil.which("uv") is None:
        print("[错误] 未找到 uv，请先安装: https://docs.astral.sh/uv/")
        print("       安装后可在项目根目录执行: uv sync")
        return 1

    settings = _load_settings()
    host = settings.app_host
    import_port = settings.import_app_port
    query_port = settings.query_app_port
    display = _browser_host(host)

    commands: list[tuple[str, list[str]]] = [
        ("Import", _uvicorn_cmd("app.api.http.import_server:app", host, import_port)),
        ("Query", _uvicorn_cmd("app.api.http.query_server:app", host, query_port)),
    ]

    processes: list[tuple[str, subprocess.Popen]] = []
    exit_code = 0

    try:
        for name, cmd in commands:
            processes.append((name, _start_process(name, cmd)))
            time.sleep(0.5)

        print()
        print("=" * 56)
        print(f"  导入 API   http://{display}:{import_port}/docs")
        print(f"  问答 API   http://{display}:{query_port}/docs")
        print(f"  问答页面   http://{display}:{query_port}/html/new")
        print(f"  登录页面   http://{display}:{query_port}/html/login")
        print(f"  导入页面   http://{display}:{query_port}/html/import")
        print("=" * 56)
        print("按 Ctrl+C 停止全部服务\n")

        while True:
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f"[退出] {name} 已停止 (code={code})")
                    exit_code = code or 1
                    return exit_code
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[停止] 收到 Ctrl+C，正在关闭服务...")
        exit_code = 0
    finally:
        _stop_processes(processes)
        print("[停止] 全部服务已关闭")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
