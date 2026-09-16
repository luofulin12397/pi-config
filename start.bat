@echo off
chcp 65001 >nul
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo.
    echo [错误] 未找到 uv，请先安装: https://docs.astral.sh/uv/
    echo        安装后在项目根目录执行: uv sync
    pause
    exit /b 1
)

echo.
echo 正在启动 RAG 双服务 (uv run, Import + Query) ...
echo.

uv run python scripts\run_servers.py
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
    echo.
    echo 启动失败，退出码: %ERR%
    pause
)
exit /b %ERR%
