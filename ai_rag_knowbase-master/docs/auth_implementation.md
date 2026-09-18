# 用户鉴权 — 技术实现文档

## 1. 架构概览

```
前端 login.html / chat_new.html / import_new.html
        │  Authorization: Bearer JWT
        ▼
FastAPI (query_server :8001 / import_server :8000)
        │  auth_routes.py  /auth/*
        │  deps.get_current_user
        ▼
MongoDB (enterprise_rag)
  ├── users
  ├── roles
  ├── user_roles
  ├── refresh_tokens
  └── document_permissions
```

**说明**：Query 流程中的主体权限过滤（`permission_service`）尚未实现，当前仅完成登录鉴权 + 导入时写入文档权限元数据。

---

## 2. MongoDB 集合设计

### auth_users / auth_roles / auth_user_roles / auth_refresh_tokens

> 使用 `auth_` 前缀，避免与 MongoDB 中已有 `users` 等业务集合冲突。

#### auth_users

| 字段 | 类型 | 说明 |
|------|------|------|
| username | string | 唯一 |
| password_hash | string | bcrypt |
| display_name | string | 展示名 |
| status | string | active / disabled |
| created_at / updated_at / last_login_at | datetime | |

#### auth_roles

| 字段 | 类型 | 说明 |
|------|------|------|
| code | string | 唯一，如 admin |
| name | string | 中文名 |
| description | string | |

#### auth_user_roles

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | ObjectId | |
| role_code | string | |
| granted_at | datetime | |

#### auth_refresh_tokens

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | ObjectId | |
| token_hash | string | SHA256，不存明文 |
| expires_at | datetime | |
| revoked | bool | |

### document_permissions

| 字段 | 类型 | 说明 |
|------|------|------|
| file_title | string | 文件名（无后缀） |
| item_name | string | LLM 识别主体 |
| allowed_roles | string[] | 可读角色 |
| imported_by | string | 导入用户 ID |
| task_id | string | 导入任务 ID |

---

## 3. 后端文件结构

```
app/
├── api/
│   ├── http/auth_routes.py       # /auth/* 路由
│   └── schema/auth_schema.py     # Pydantic 模型
├── infra/
│   ├── persistence/
│   │   ├── auth_repository.py
│   │   └── permission_repository.py
│   └── security/
│       ├── deps.py               # get_current_user / get_current_user_sse
│       ├── jwt_utils.py
│       └── password_utils.py
├── shared/
│   ├── clients/mongo_auth_utils.py
│   └── config/auth_config.py
└── resources/html/
    ├── auth.js                   # 前端鉴权工具
    ├── login.html
    ├── chat_new.html             # 已接入鉴权
    └── import_new.html           # 已接入鉴权 + 角色选择

scripts/seed_auth.py              # 种子数据
docs/auth_api.md                  # 接口文档
```

---

## 4. 环境变量

```env
JWT_SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_REFRESH_TOKEN_REMEMBER_DAYS=30
MONGO_URL=mongodb://127.0.0.1:27017
MONGO_DB_NAME=enterprise_rag
```

---

## 5. 启动与联调步骤

### 5.1 安装依赖

```bash
uv sync
```

### 5.2 初始化种子数据

```bash
python scripts/seed_auth.py
```

### 5.3 启动服务

**方式一：一键启动（推荐）**

```bash
uv run python scripts/run_servers.py
```

**方式二：分别启动两个终端**

```bash
uvicorn app.api.http.import_server:app --host 0.0.0.0 --port 8000
uvicorn app.api.http.query_server:app --host 0.0.0.0 --port 8001
```

### 5.4 访问流程

1. 打开 `http://127.0.0.1:8001/html/login` 登录
2. 登录成功后跳转问答页；侧栏可进导入页（8000）
3. 导入页选择文档权限角色后上传
4. 导入完成后 MongoDB `document_permissions` 写入记录

---

## 6. 导入权限写入时机

[`import_server.invoke_graph`](app/api/http/import_server.py) 在 LangGraph 全流程成功后调用：

```python
permission_repository.upsert_document_permission(
    file_title=final_state.get("file_title"),
    item_name=final_state.get("item_name"),
    allowed_roles=allowed_roles,
    imported_by=imported_by,
    task_id=task_id,
)
```

`ImportGraphState` 已扩展 `allowed_roles`、`imported_by` 字段（Milvus 写入权限字段留待下一阶段）。

---

## 7. 前端鉴权机制

[`auth.js`](app/resources/html/auth.js) 提供：

- `RagAuth.login` / `logout` / `requireAuth`
- `RagAuth.authFetch` — 自动带 Token，401 时 refresh 重试
- `RagAuth.bindUserSidebar` — 更新侧栏用户信息

SSE 流式：`EventSource` 不支持 Header，使用 `?token=` 传 Access Token，后端 `get_current_user_sse` 校验。

---

## 8. 后续待做（Query 权限过滤）

- 在 `node_item_name_confirm` 之后增加权限校验
- `QueryGraphState` 增加 `denied_item_names`
- Milvus chunk 集合增加 `allowed_roles` 字段
- 检索 expr 扩展（当前 **未实现**）
