# 一键启动 Import(:8000) + Query(:8001)，使用 uv run
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "[错误] 未找到 uv，请先安装: https://docs.astral.sh/uv/" -ForegroundColor Red
    Write-Host "       安装后在项目根目录执行: uv sync"
    exit 1
}

Write-Host ""
Write-Host "正在启动 RAG 双服务 (uv run, Import + Query) ..." -ForegroundColor Cyan
Write-Host ""

uv run python scripts/run_servers.py
exit $LASTEXITCODE
