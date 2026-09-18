#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# 打「可下载部署包」：只含代码 + 部署配置，排除密钥、运行产物、大数据与版本库
#
#   bash scripts/package_release.sh
#   → release/rag-knowbase-<时间戳>.tar.gz （含 sha256 校验文件）
#
# 目标机：解包 → cp .env.example .env → 填值 → docker compose -f deploy/docker-compose.full.yml up -d --build
#
# 实现注意（勿回退）：
#   1) tar 以 `-C 父目录 包名` 打包，归档内路径形如 <包名>/output，
#      因此 --exclude 模式必须带 <包名> 前缀，不能写 ./output
#   2) 安全校验不把 tar 列表塞进变量再走管道：`echo "$大字符串" | grep -q`
#      会因 grep 提前退出产生 SIGPIPE，在 set -o pipefail 下被判定为失败，
#      导致「命中禁止项」永远检测不到。改为先落盘再对文件 grep。
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="$(dirname "$ROOT")"
PKG_NAME="$(basename "$ROOT")"
OUT_DIR="${ROOT}/release"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="${OUT_DIR}/rag-knowbase-${STAMP}.tar.gz"
LISTING="$(mktemp)"
trap 'rm -f "$LISTING"' EXIT

# 命中即排除（模式带包名前缀，按归档内路径匹配）
EXCLUDES=(
  "--exclude-vcs"
  "--exclude=${PKG_NAME}/.env"
  "--exclude=${PKG_NAME}/.env.*"
  "--exclude=${PKG_NAME}/.venv"
  "--exclude=${PKG_NAME}/output"
  "--exclude=${PKG_NAME}/logs"
  "--exclude=${PKG_NAME}/doc"
  "--exclude=${PKG_NAME}/models"
  "--exclude=${PKG_NAME}/release"
  "--exclude=${PKG_NAME}/node_modules"
  "--exclude=${PKG_NAME}/.pytest_cache"
  "--exclude=${PKG_NAME}/.ruff_cache"
  "--exclude=${PKG_NAME}/__pycache__"
  "--exclude=*/__pycache__"
  "--exclude=*.pyc"
)

mkdir -p "$OUT_DIR"
echo "[打包] 源目录：${ROOT}"
echo "[打包] 输出：${ARCHIVE}"

tar "${EXCLUDES[@]}" -czf "$ARCHIVE" -C "$PARENT" "$PKG_NAME"
tar -tzf "$ARCHIVE" > "$LISTING"

# ── 安全校验：确认包里没有密钥与产物（.env.example 允许存在）────────────────
echo "[校验] 检查是否误打包 .env / 运行产物 ..."
FAIL=0
while IFS= read -r pattern; do
  [ -z "$pattern" ] && continue
  if grep -qE "$pattern" "$LISTING"; then
    echo "  ✗ 命中禁止项：$pattern（例：$(grep -m1 -E "$pattern" "$LISTING")）"
    FAIL=1
  fi
done <<'PATTERNS'
(^|/)\.env$
(^|/)\.env\.(local|dev|prod|test)
(^|/)output/
(^|/)logs/
(^|/)doc/
(^|/)models/
(^|/)\.venv/
__pycache__/
PATTERNS
if ! grep -qE '(^|/)\.env\.example$' "$LISTING"; then
  echo "  ! 警告：包内缺少 .env.example，目标机将无从配置"
fi
if [ "$FAIL" = "1" ]; then
  rm -f "$ARCHIVE"
  echo "[失败] 包内含敏感/冗余内容，已删除产物。请检查 EXCLUDES 列表。"
  exit 1
fi

sha256sum "$ARCHIVE" > "${ARCHIVE}.sha256"
echo "[完成] ${ARCHIVE} ($(du -h "$ARCHIVE" | cut -f1))"
echo "[完成] 校验文件：${ARCHIVE}.sha256"
echo "       包内文件数：$(wc -l < "$LISTING")"
echo
echo "拷到目标机："
echo "  scp ${ARCHIVE} user@目标机:/opt/"
echo "目标机上："
echo "  tar -xzf rag-knowbase-*.tar.gz && cd ${PKG_NAME}"
echo "  cp .env.example .env && cp deploy/.env.example deploy/.env   # 填密钥与 PUBLIC_HOST"
echo "  docker compose -f deploy/docker-compose.full.yml up -d --build"
echo "  open http://<目标机IP>:55001/console/"
