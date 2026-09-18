# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# RAG 智库管理平台 · 应用镜像（导入 :55000 / 问答与管理 :55001 共用同一镜像）
#
# 构建：
#   docker build -t rag-app:local .                    # 瘦镜像（默认，推荐）
#   docker build -t rag-app:local --build-arg SLIM=0 . # 全量依赖（与开发环境完全一致，体积大数倍）
# 换索引源（默认清华源；海外可改 pypi.org）：
#   docker build -t rag-app:local --build-arg UV_INDEX_URL=https://pypi.org/simple
#
# SLIM 实现方式：deploy/requirements.deploy.txt 由
#   scripts/gen_deploy_requirements.py 从 uv.lock 做「依赖图可达性分析」生成，
#   剔除 app/ 零导入的重依赖（torch/CUDA、flagembedding、magic-pdf、unstructured、
#   transformers、datasets、modelscope、pymilvus-model）及其传递依赖。
#   不用 `uv sync --no-install-package` 的原因：它只剔除指定包本身，其传递依赖
#   （如 torch 带来的数 GB nvidia-cu12 系列）仍会被装上。
#   若将来启用本地模型或离线解析：用 SLIM=0，或改 DROP_ROOTS 后重新生成依赖清单。
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH

ARG UV_VERSION=0.12.15
# 依赖索引：默认清华源（本项目锁文件即由该源解析，且本机实测 pypi.org 不可达）
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" "uv==${UV_VERSION}"

WORKDIR /app

# ── 依赖层：先只 COPY 依赖清单，源码变更不会击穿缓存 ──────────────────────────
COPY pyproject.toml uv.lock ./
COPY deploy/requirements.deploy.txt ./deploy/

ARG SLIM=1
# 不使用 BuildKit 专有语法（--mount / --check），保证无 buildx 的环境也能构建
RUN set -eu; \
    if [ "$SLIM" = "1" ]; then \
      uv pip install --system --no-cache --index-url "$UV_INDEX_URL" \
        -r deploy/requirements.deploy.txt; \
    else \
      uv sync --frozen --no-dev --no-install-project; \
    fi

# ── 源码层 ──────────────────────────────────────────────────────────────────
# console/ 由 query_server 挂载到 /console（Path(__file__).parents[3] 即 /app）
COPY app/ ./app/
COPY console/ ./console/
COPY scripts/ ./scripts/

# 运行期可写目录（compose 会挂载为卷，避免容器重建丢产物）
RUN mkdir -p /app/output /app/logs

EXPOSE 55000 55001

# 默认启动问答与管理服务；导入服务由 docker-compose 覆盖 command
CMD ["uvicorn", "app.api.http.query_server:app", "--host", "0.0.0.0", "--port", "55001"]
