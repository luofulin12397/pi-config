# RAG 智库管理平台 — 部署与使用说明

> 需求依据：《知识管理平台.md》（需求 2.9）。本文档面向部署与演示人员。

## 一、系统组成

| 组件 | 地址 | 说明 |
|---|---|---|
| 导入服务 | :55000 | 文档上传/解析/切片/向量化（FastAPI） |
| 问答与管理服务 | :55001 | 问答（SSE）、知识台账、权限、FAQ、看板、**控制台前端** |
| 控制台 | http://<host>:55001/console/ | 单端口部署，无 CORS |
| MongoDB | :27017 | 用户/角色/知识台账/权限/FAQ/缺口/审计日志（容器） |
| Milvus + etcd + MinIO | :19530 / :9000 | 向量库与对象存储（容器，compose 一键） |

## 二、快速启动（全新机器）

```bash
# 1. 基础环境（一次性）
apt-get install -y docker.io docker-compose-v2   # 容器
cd ai_rag_knowbase-master && uv venv --python 3.12 && \
  uv pip install --index-url https://mirrors.aliyun.com/pypi/simple \
  fastapi "uvicorn[standard]" pydantic pydantic-settings python-dotenv python-multipart \
  langchain langchain-core langchain-openai langchain-community langgraph grandalf \
  pymilvus minio pymongo bcrypt pyjwt loguru httpx numpy requests redis openai-agents python-docx

# 2. 配置 .env（关键项）
#    OPENAI_API_KEY/OPENAI_BASE_URL  → DeepSeek（chat）
#    EMBEDDING_API_KEY/EMBEDDING_API_BASE/EMBEDDING_MODEL → 硅基流动 bge-m3
#    RERANK_API_KEY/RERANK_API_BASE/RERANK_MODEL → 硅基流动 reranker
#    MILVUS_URL/MONGO_URL/MINIO_ENDPOINT → 127.0.0.1（compose 默认）
#    JWT_SECRET_KEY → 必须改为长随机串

# 3. 中间件
docker compose -f deploy/docker-compose.yml up -d

# 4. 种子数据（角色/管理员）+ 演示日志（可选：看板/挖掘演示数据）
.venv/bin/python scripts/seed_auth.py
.venv/bin/python scripts/seed_qalogs.py

# 5. 双服务
nohup .venv/bin/python -m uvicorn app.api.http.import_server:app --host 0.0.0.0 --port 55000 > logs/import-server.log 2>&1 &
nohup .venv/bin/python -m uvicorn app.api.http.query_server:app  --host 0.0.0.0 --port 55001 > logs/query-server.log 2>&1 &
```

## 三、演示账号

| 账号 | 密码 | 角色 | 部门 | 用途 |
|---|---|---|---|---|
| admin | admin123 | 系统管理员 | — | 全部功能（知识中心/沉淀/看板/组织） |
| zhangsan | zhang123 | 普通员工（common_user） | dept-biz | 问答工作台；问薪酬会收到权限受限提示 |
| zhaoliu | zhao123 | 管理层（r_mgmt） | dept-gm | 问答工作台；薪酬文档可见 |

## 四、端到端演示

### 场景一：跨部门权限隔离
1. admin 登录控制台 → 知识维护与导入 → 对《高管薪酬与股权激励细则》配权限：部门 dept-hr + 角色 r_mgmt
2. zhangsan 登录 → 问答工作台问「差旅报销…」正常回答；问「高管薪酬…」→ 受限提示零泄露
3. zhaoliu 登录 → 同题正常回答

### 场景二：FAQ 沉淀与缺口闭环
1. 沉淀与运营 → 立即挖掘 → FAQ 候选出现高频问题簇（含频次）
2. 在线润色答案 → 审核发布（写入缓存）→ 问答工作台同义提问毫秒直出（来源标签=FAQ 缓存）
3. 知识缺口 tab → 未命中问题聚合 → 转知识补全任务

一键脚本：`.venv/bin/python scripts/test_m1_scenario.py`（场景一 10 项）、`scripts/test_m3_sediment.py`（沉淀 8 项）。

## 五、验收脚本清单

| 脚本 | 覆盖 |
|---|---|
| scripts/test_m1_ledger.py | 台账/导入/停用过滤/删除（9 项） |
| scripts/test_m1_perms.py | 四维权限配置/按钮级拒绝/默认拒绝（6 项） |
| scripts/test_m1_scenario.py | 需求 2.9.9 场景一端到端（10 项） |
| scripts/test_m1_sse.py | SSE 六步事件流/delta/refs/done（9 项） |
| scripts/test_m3_sediment.py | 审计+FAQ 直出+缺口+看板（8/12 项） |
| scripts/test_m4_formats.py | TXT/DOCX 导入与权限联动（4 项） |

## 六、常见问题

- **安全组**：对外访问需放行 55001（控制台+API）；55000 可仅内网（前端经代理访问）
- **PDF 解析**：依赖 MinerU API（.env MINERU_*）；MD/TXT/DOCX 不依赖
- **硅基流动 503**：免费端点偶发限流，embedding 已内置 5 次退避重试；持续 503 稍后重试
- **Redis 未配置**：自动回退进程内存（多 worker 部署时建议配置）
- **JWT_SECRET_KEY**：生产必须替换（启动时有警告）
- **API Key 轮换**：改 .env 后重启双服务即可
