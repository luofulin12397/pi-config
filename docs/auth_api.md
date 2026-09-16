# 用户鉴权 — 前端接口文档

> Base URL：Query 服务 `http://127.0.0.1:8001`，Import 服务 `http://127.0.0.1:8000`（两套服务均挂载相同 `/auth/*` 路由）

## 通用约定

### 响应结构

```json
{
  "code": 200,
  "message": "ok",
  "data": {}
}
```

### 认证 Header

除白名单外，请求需携带：

```
Authorization: Bearer <access_token>
```

### 白名单（无需 Token）

| 路径 | 说明 |
|------|------|
| `GET /html/login` | 登录页 |
| `GET /static/auth.js` | 鉴权 JS |
| `POST /auth/login` | 登录 |
| `POST /auth/refresh` | 刷新 Token |
| `GET /health` | 健康检查（仅 Query 服务） |

---

## 接口列表

### POST `/auth/login` — 登录

**Body**

```json
{
  "username": "admin",
  "password": "admin123",
  "remember_me": true
}
```

**Response 200**

```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "access_token": "eyJ...",
    "token_type": "Bearer",
    "expires_in": 1800,
    "refresh_token": "xxx",
    "user": {
      "id": "...",
      "username": "admin",
      "display_name": "系统管理员",
      "roles": ["admin"]
    }
  }
}
```

---

### POST `/auth/refresh` — 刷新 Access Token

**Body**

```json
{ "refresh_token": "xxx" }
```

**Response 200**

```json
{
  "code": 200,
  "message": "刷新成功",
  "data": {
    "access_token": "eyJ...",
    "token_type": "Bearer",
    "expires_in": 1800
  }
}
```

---

### POST `/auth/logout` — 注销

需 Header `Authorization: Bearer <access_token>`

**Body（可选）**

```json
{ "refresh_token": "xxx" }
```

---

### GET `/auth/me` — 当前用户

需登录。

---

### GET `/auth/roles` — 角色列表

导入页权限多选用。需登录。

**Response data 示例**

```json
[
  { "code": "admin", "name": "管理员", "description": "..." },
  { "code": "product_a_reader", "name": "产品A阅读者", "description": "..." }
]
```

---

### GET `/auth/permissions` — 文档权限列表

查询已导入文档的权限记录（MongoDB `document_permissions`）。需登录。

---

## 受保护的 Query 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/query` | 提问 |
| GET | `/stream/{session_id}?token=` | SSE 流（Token 放 query，因 EventSource 不支持 Header） |
| GET | `/history/{session_id}` | 历史记录 |
| DELETE | `/history/{session_id}` | 清空历史 |

---

## 受保护的 Import 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传（multipart，额外字段 `allowed_roles` JSON 数组字符串） |
| GET | `/status/{task_id}` | 任务状态 |

**上传示例**

```
POST /upload
Content-Type: multipart/form-data
Authorization: Bearer <token>

files: <file>
allowed_roles: ["admin","product_a_reader"]
```

---

## 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | admin |
| user_a | user123 | product_a_reader, common_user |
| user_b | user123 | product_b_reader, common_user |

初始化：``python scripts/seed_auth.py``

---

## 页面入口

| 页面 | URL |
|------|-----|
| 登录 | `http://127.0.0.1:8001/html/login` |
| 问答（唯一入口） | `http://127.0.0.1:8001/html/new` |
| 导入 | `http://127.0.0.1:8001/html/import`（须从问答页跳转，不可直接访问） |

> Import 服务 `:8000` 不再提供 HTML 页面，访问 `/html/*` 将 302 跳转到问答页。
