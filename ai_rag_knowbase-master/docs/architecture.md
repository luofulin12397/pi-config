---
last_updated: 2026-07-17
status: active
---
# ai_0119_rag - 详细架构

## 项目定位

企业级 RAG 知识库问答平台，实现「上传文档 → 解析切片 → 向量入库 → 知识检索 → LLM 生成」完整链路。
双服务架构：导入服务（:55000）负责文档处理，问答服务（:55001）负责知识检索与对话。

## 技术栈

| 组件 | 选型 | 用途 |
|---|---|---|
| 后端框架 | FastAPI + Uvicorn | 双服务 HTTP 入口 |
| LLM 调用 | LangChain ChatOpenAI | 统一 OpenAI 兼容 API（兼容通义千问、DeepSeek 等） |
| 流程编排 | LangGraph | 导入/查询 Agent 有向图编排 |
| 向量数据库 | Milvus | 稠密+稀疏混合向量存储与检索 |
| 嵌入模型 | BAAI/bge-m3 (FlagEmbedding) | 生成稠密+稀疏混合向量 |
| 重排模型 | BAAI/bge-reranker-v2-m3 | Cross-Encoder 精排 |
| 文档解析 | MinerU API | PDF 转 Markdown |
| 对象存储 | MinIO | Markdown 图片存储 |
| 业务数据库 | MongoDB | 用户、角色、权限、任务、对话历史、语义缓存 |
| 会话缓存 | Redis（可选） | 跨 worker SSE 会话共享（未配置时回退内存） |
| 包管理 | uv | Python 依赖管理 |

## 项目结构

（见模块清单部分，项目结构已在模块清单中以表格呈现）

## 模块清单

| 模块 | 路径 | 职责说明 |
|---|---|---|
| API 路由 - 导入 | app/api/http/import_server.py | 文件上传、任务提交/状态查询/删除 |
| API 路由 - 问答 | app/api/http/query_server.py | 知识问答、SSE 流式、文档预览、静态页面 |
| API 路由 - 认证 | app/api/http/auth_routes.py | 登录/刷新/登出/角色/权限接口 |
| LLM 封装 | app/infra/llm/providers.py | 文本/视觉模型、Embedding、Reranker 统一入口 |
| 对象存储 | app/infra/object_storage/ | MinIO 文件上传/下载/删除 |
| 用户持久化 | app/infra/persistence/auth_repository.py | 用户/角色/Token 的 MongoDB CRUD |
| 历史持久化 | app/infra/persistence/history_repository.py | 对话历史 MongoDB CRUD |
| 导入任务持久化 | app/infra/persistence/import_task_repository.py | 导入任务 MongoDB CRUD |
| 权限持久化 | app/infra/persistence/permission_repository.py | 文档权限 MongoDB CRUD |
| 缓存持久化 | app/infra/persistence/qa_cache_repository.py | 语义缓存 MongoDB CRUD |
| 认证依赖 | app/infra/security/deps.py | FastAPI 鉴权依赖（CurrentUser） |
| JWT 工具 | app/infra/security/jwt_utils.py | Access/SSE Token 签发解析 |
| 密码工具 | app/infra/security/password_utils.py | bcrypt 哈希/校验 |
| 角色工具 | app/infra/security/role_utils.py | 角色常量 + 导入权限校验 |
| 向量网关 | app/infra/vectorstore/milvus_gateway.py | Milvus 集合管理/CRUD/搜索 |
| 导入 Agent | app/process/import_/agent/ | LangGraph 7 节点编排文档导入 |
| 查询 Agent | app/process/query/agent/ | LangGraph 11 节点编排知识问答 |
| 导入服务 | app/rag/import_/ | PDF 解析、切片、Embedding、索引 |
| 查询服务 | app/rag/query/ | 检索、重排序、RAG 生成、缓存 |
| MongoDB 客户端 | app/shared/clients/ | Mongo/Milvus/MinIO/Redis 客户端封装 |
| 配置定义 | app/shared/config/ | 所有模块的 Pydantic Settings 配置 |
| AI 模型工具 | app/shared/model/ | Embedding/LLM/Reranker 统一调用 |
| 运行时 | app/shared/runtime/ | loguru 日志 + Prompt 模板加载 |
| 工具函数 | app/shared/utils/ | 任务管理、SSE、频率限制等 |

## 数据流

### 文档导入流程

用户 -> POST /upload (import_server.py)
  -> 存文件到 output/YYYYMMDD/{task_id}/
  -> 后台 invoke_graph()
  -> process/import_/agent/ (LangGraph)
    1. node_entry -> 判断文件类型（PDF/MD）
       - PDF -> node_pdf_to_md -> MinerU API 上传PDF -> 轮询结果 -> 下载ZIP -> 解压 -> 提取MD
       - MD  -> 直接到 node_md_img
    2. node_md_img -> 解析MD中图片 -> LLM 生成图片摘要 -> 上传 MinIO -> 替换 MD 图片链接
    3. node_document_split -> 按章节/段落切片
    4. node_item_name_recognition -> LLM 识别文档主体名 -> 写入 Milvus kb_item_names
    5. node_bge_embedding -> BGE-M3 生成稠密+稀疏混合向量
    6. node_import_milvus -> 写入 Milvus kb_chunks（含向量/metadata）
  -> 落库 MongoDB import_tasks（状态完成/失败）
  -> 落库 MongoDB document_permissions（文档角色权限）

### 知识问答流程

用户 -> POST /query (query_server.py) -> 同步/异步 + SSE 流式
  -> process/query/agent/ (LangGraph 11 节点)
    1. node_query_cache
       - 命中缓存 -> 直接返回 answer -> END
       - 未命中 -> 继续
    2. node_history_compress -> LLM 压缩历史对话摘要
    3. node_item_name_confirm -> LLM 从问题提取商品主体名
    4. node_access_control -> 根据用户角色过滤无权限商品
       - 无匹配商品 -> 直接提示"请确认商品"
       - 有匹配商品 -> 三路并行检索
    5. node_search_embedding -> Milvus 稠密向量检索（BGE-M3）
    6. node_search_embedding_hyde -> LLM HyDE 生成假设文档 -> 向量检索
    7. node_web_search_mcp -> DashScope WebSearch MCP
    8. node_rrf -> 三路结果 Reciprocal Rank Fusion 融合
    9. node_rerank -> BGE-Reranker Cross-Encoder 精排
    10. node_answer_output
        - 组装 Prompt（参考内容+历史+商品+问题+越权提醒）
        - LLM 生成答案（流式 SSE / 非流式完整返回）
        - 提取答案中图片 URL + 构建引用来源 + 追加引用区块
        - 写回 history（MongoDB chat_message）
    11. node_save_cache -> 语义缓存写入 MongoDB qa_cache

## 模块依赖关系

| 模块 | 依赖的模块 | 说明 |
|---|---|---|
| app/api/http/import_server | infra/persistence, infra/security, process/import_, rag/import_, shared/runtime | 导入路由 |
| app/api/http/query_server | infra/persistence, infra/security, process/query_, rag/query, shared/runtime | 问答路由 |
| app/api/http/auth_routes | infra/persistence, infra/security, shared/config, shared/runtime | 认证路由 |
| app/process/import_/agent/ | rag/import_, shared/runtime, shared/utils | Agent 编排 RAG 导入服务 |
| app/process/query/agent/ | rag/query, shared/runtime, shared/utils | Agent 编排 RAG 查询服务 |
| app/rag/import_/ | infra/llm, infra/vectorstore, infra/object_storage, infra/config, shared/runtime | RAG 导入业务 |
| app/rag/query/ | infra/llm, infra/vectorstore, infra/persistence, shared/config, shared/runtime | RAG 查询业务 |
| app/infra/llm | shared/model, shared/config | LLM 封装 |
| app/infra/vectorstore | shared/clients | Milvus 网关 |
| app/infra/persistence | shared/clients | Repository 层 |
| app/infra/security | shared/config | 安全模块 |
| app/shared/ | - | 共享层无内部依赖（仅第三方 SDK） |

## 关键设计决策

### 1. 双服务架构
- 原因：导入（计算密集型，PDF 解析慢）和问答（I/O 密集型，LLM 流式）是两类不同负载，分离后可独立扩缩容
- 端口：导入 :55000 / 问答 :55001
- 代价：用户认证状态需共享 MongoDB，前端在两个服务间跳转

### 2. 混合向量检索（稠密 + 稀疏）
- BGE-M3 同时输出稠密向量（1024维）和稀疏向量（SPLADE 词权重），Milvus 同时支持两种检索
- 三路并行策略：普通向量检索 + HyDE 增强检索 + Web 搜索，通过 RRF 融合排序

### 3. LangGraph Agent 流程编排
- 导入 Agent：串行 7 节点，通过 StateGraph 控制流转
- 查询 Agent：11 节点 + 条件分支，入口缓存判断 + 三路并行 + RRF + Rerank
- 节点通过 @node_log 装饰器自动记录耗时和追踪 ID

### 4. 三层架构分层
- API 层（api/）：只负责 HTTP 路由和入参校验
- RAG 服务层（rag/）：纯业务逻辑，不依赖 FastAPI
- Agent 流程层（process/）：LangGraph 有向图编排
- 每层通过 infra/ 封装基础设施，通过 shared/ 共享配置和工具

### 5. 语义缓存
- LLM 判断两轮问题语义相似度（非传统文本哈希）
- 按 knowledge_version 隔离，版本更新后旧缓存自动失效
- MongoDB TTL 索引自动过期

### 6. 配置驱动
- 所有配置通过 .env + dataclass 读取，集中管理在 shared/config/
- LLM 供应商使用 OpenAI 兼容 API，可切换通义千问/DeepSeek/OpenAI

### 7. 外部依赖
- MinerU（阿里开源 PDF 解析）：核心 PDF 转 MD 能力依赖外部 API，需联网 + API Token
- DashScope MCP（百炼平台）：Web 搜索功能依赖阿里百炼 MCP 服务
- BGE-M3 / BGE-Reranker：本地加载 HuggingFace 模型，首次需下载

## 安全设计

- JWT 双 Token：短期 Access Token（30min）+ 长期 Refresh Token（7d/30d）
- SSE 专有 Token：5 分钟短效，避免 Access Token 暴露在 URL
- RBAC 角色鉴权：admin / common_user 两级，文档按角色授权
- 导入权限校验：非 admin 不能为文档分配自己不具备的角色
- bcrypt 密码哈希，Refresh Token 用 SHA256 哈希存储
- 登录频率限制：10 次/5 分钟
- 生产环境 JWT 密钥硬校验（启动时检测默认值）