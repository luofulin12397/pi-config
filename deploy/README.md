# 部署说明（Docker Compose 完整栈）

目标：把仓库拷到一台新机器，一条命令起全栈（4 个数据服务 + 2 个应用服务），不依赖宿主机 Python/uv。

## 1. 前置要求

| 项 | 要求 |
|---|---|
| Docker | 24+（含 compose v2，`docker compose version` 可用） |
| 内存 | 建议 ≥ 8 GB（Milvus standalone 占用较大） |
| 磁盘 | ≥ 20 GB（镜像 + 向量数据 + 导入产物） |
| 网络 | 构建镜像需拉取 PyPI 依赖；国内可用下方镜像源参数 |
| GPU | **不需要**（向量化与重排已 API 化；MinerU 走 HTTP） |

## 2. 部署步骤

```bash
# ① 解包
tar -xzf rag-knowbase-<时间戳>.tar.gz
cd ai_rag_knowbase-master

# ② 配置环境变量（两份，职责不同）
cp .env.example .env              # 应用级：密钥、模型、连接串\ cp deploy/.env.example deploy/.env  # compose 插值级：PUBLIC_HOST
vi .env && vi deploy/.env
```

> 为什么分两份：仓库根的 `.env` 由 compose 的 `env_file` 注入**容器内部**，不参与 `${...}` 插值；
> compose 只会自动读取**与 compose 文件同目录的** `deploy/.env`。

**必须修改的项**：

| 键 | 说明 |
|---|---|
| `JWT_SECRET_KEY` | 生产必须替换：`python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `APP_ENV` | 生产填 `prod`（会强校验 JWT 密钥与 CORS） |
| `CORS_ORIGINS` | 生产写具体域名 |
| `PUBLIC_HOST` | **写进 `deploy/.env`**：服务器 IP 或域名（用于拼接浏览器可访问的图片地址，见第 4 节） |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | LLM 与视觉模型 |
| `EMBEDDING_API_KEY` / `RERANK_API_KEY` | 向量化与重排（当前实现走 SiliconFlow API） |
| `MINERU_API_TOKEN` | PDF 解析 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 建议改掉默认 minioadmin |

```bash
# ③ 构建并启动
docker compose -f deploy/docker-compose.full.yml up -d --build

# 国内网络构建慢/失败时，改用镜像源
docker compose -f deploy/docker-compose.full.yml build \
  --build-arg UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

# ④ 验证
docker compose -f deploy/docker-compose.full.yml ps
curl -fsS http://localhost:55001/health
open http://<服务器IP>:55001/console/     # 控制台入口
```

首次启动 Milvus 需要建集合与加载模型，等 1–2 分钟再访问。

## 3. 常用运维

```bash
docker compose -f deploy/docker-compose.full.yml logs -f query-service   # 看日志
docker compose -f deploy/docker-compose.full.yml restart query-service   # 重启单服务
docker compose -f deploy/docker-compose.full.yml down                     # 停止（保留数据卷）
docker compose -f deploy/docker-compose.full.yml up -d --build            # 更新代码后重建
```

数据持久化：MongoDB / Milvus / MinIO 分别落在 4 个具名卷；导入产物与日志挂到仓库同级的 `output/`、`logs/`。
**不要**用 `down -v`（会删除向量库与用户数据）。

## 4. 常见问题

### 图片显示不出来
`MINIO_ENDPOINT` 会被拼进 Markdown 图片 URL **并交给浏览器访问**（见 `app/infra/object_storage/minio_gateway.py: build_image_url`）。
所以容器的 MinIO 地址**不能**填 `minio:9000`——那是容器内网地址，浏览器解析不了。

本 compose 已处理为 `MINIO_ENDPOINT=${PUBLIC_HOST:-host.docker.internal}:9000`：
- 把 `deploy/.env` 的 `PUBLIC_HOST` 设为服务器 IP/域名（如 `192.168.1.10`）——已验证插值生效
- 不改则回退 `host.docker.internal`（仅适用于浏览器也在同一台机器上的场景）
- 同时要求宿主机的 9000 端口可被浏览器访问（本 compose 已映射）
- 临时覆盖也可用 shell 变量：`PUBLIC_HOST=1.2.3.4 docker compose -f deploy/docker-compose.full.yml up -d`

### 端口冲突
`deploy/docker-compose.full.yml`（全栈）与 `deploy/docker-compose.yml`（只跑数据服务、供宿主机 `uv run` 调试）**端口相同**，不要同时启动。

### 想用本地模型而不是 API
1. 构建全量依赖镜像：`--build-arg SLIM=0`（会装 torch/CUDA，体积大幅增加）
2. `.env` 填 `BGE_M3_PATH` / `BGE_RERANKER_LARGE` 指向模型目录，并挂载进容器
3. `.env` 设 `BGE_DEVICE=cuda` 时需目标机有 NVIDIA 驱动 + nvidia-container-toolkit，并在 compose 中为服务加 GPU 预留：
   ```yaml
   deploy:
     resources:
       reservations:
         devices: [{ driver: nvidia, count: 1, capabilities: [gpu] }]
   ```

### 内存不足 / Milvus 起不来
Milvus standalone 首次启动会拉取并加载索引，内存不足时会不断重启。先 `docker compose ... logs milvus` 看原因，再考虑升配或改用 Milvus Lite / 远程 Milvus（把 `MILVUS_URL` 指向外部实例即可，无需本地 milvus 服务）。

## 5. 与开发模式的关系

| 场景 | 用什么 |
|---|---|
| 本机开发（热重载、改代码即生效） | `uv sync` + `start.ps1`（宿主机 uv run，数据服务用 `deploy/docker-compose.yml`） |
| 目标机部署 / 演示 | 本文件（全容器化） |
| 只更新应用代码 | `docker compose -f deploy/docker-compose.full.yml up -d --build import-service query-service` |

## 6. 已验证项（实测记录）

| 项 | 结果 |
|---|---|
| `docker compose -f deploy/docker-compose.full.yml config` | 通过（6 服务；容器网络地址 `mongo/milvus` 与 `MINIO_ENDPOINT` 替换正确） |
| `docker build -t rag-app:local .` | 通过，镜像 **815 MB** |
| 容器内导入双服务 | 通过（import_server 18 路由 / query_server 52 路由） |
| 容器启动冒烟 | `/health` → 200 `{"code":200,"message":"可以访问!!"}`；`/console/` → 200 |
| 打包脚本 | 产出 1.4 MB / 245 文件，校验未含 `.env` 与运行产物 |
| 未验证 | 未在本机跑完整 6 服务栈（会与开发用容器抢 27017/19530/9000 端口）；GPU/本地模型模式未验证 |

瘦依赖清单基准：`deploy/requirements.deploy.txt`（111 包）由
`scripts/gen_deploy_requirements.py` 从 `uv.lock`（234 包）做依赖图可达性分析生成。
pyproject 变更后请重新生成，并用 `--check` 在 CI 中校验是否过期。
