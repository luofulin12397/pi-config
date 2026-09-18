# 新界面待实现接口

核心接口（问答 `/query`、`/stream`、`/history`；导入 `/upload`、`/status`）已实现，以下为 `chat_new.html` / `import_new.html` 仍缺的后端能力。

---

## 问答服务（`:8001`）

### 1. 扩展问答响应（推荐：并入 `POST /query` 非流式响应 与 SSE `final` 事件）

```json
{
  "answer": "...",
  "image_urls": [],

  "citations": [
    {
      "name": "万用表使用手册.pdf",
      "file_title": "万用表使用手册.pdf",
      "page": "12",
      "title": "第三章 电池更换",
      "score": 0.89,
      "url": "https://example.com/docs/manual.pdf#page=12"
    }
  ],

  "usage": {
    "prompt_tokens": 1200,
    "completion_tokens": 350,
    "total_tokens": 1550
  },

  "cache_hit": false,

  "related_questions": [
    "万用表如何校准？",
    "电池型号是什么？"
  ],

  "item_names": ["混合万用表"],
  "options": ["混合万用表", "数字万用表"]
}
```

| 字段 | 用途 |
|------|------|
| `citations` / `references` | 右侧「引用来源」 |
| `usage.total_tokens` | 回答底部 Token 统计 |
| `cache_hit` | 右侧缓存 Hit/Miss |
| `related_questions` | 右侧「相关问题推荐」 |
| `item_names` / `options` | 主体确认选项（可选，也可从 `answer` 文案解析） |

---

### 2. 推荐问题（可选独立接口）

```
GET /suggestions?session_id={session_id}&limit=5
```

```json
{
  "session_id": "sess-abc123",
  "items": ["向量数据库如何选型？", "Embedding 模型对比"]
}
```

---

### 3. 图片上传（多模态，可选）

```
POST /upload_image
Content-Type: multipart/form-data
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | File | 图片 |
| `session_id` | string | 可选 |

```json
{
  "code": 200,
  "image_url": "https://example.com/uploads/xxx.png"
}
```

`POST /query` 请求体需支持：

```json
{
  "query": "这张图片是什么？",
  "session_id": "sess-abc123",
  "is_stream": true,
  "image_urls": ["https://example.com/uploads/xxx.png"]
}
```

---

## 导入服务（`:8000`）

### 1. 扩展任务状态（推荐：并入 `GET /status/{task_id}`）

```json
{
  "code": 200,
  "task_id": "uuid",
  "status": "completed",
  "done_list": ["upload_file", "pdf_to_md", "document_split", "bge_embedding", "import_milvus"],
  "running_list": [],
  "detail": {
    "file_name": "产品手册.pdf",
    "file_size": 2048000,
    "file_ext": "pdf",
    "chunk_count": 128,
    "embedding_count": 128,
    "created_at": "2026-06-12T10:30:00",
    "updated_at": "2026-06-12T10:32:15",
    "preview_url": "https://example.com/output/{task_id}/产品手册.pdf"
  }
}
```

| 字段 | 用途 |
|------|------|
| `detail.chunk_count` | 文档详情 — Chunk 数量 |
| `detail.embedding_count` | 文档详情 — Embedding 数量 |
| `detail.preview_url` | 「预览文档」按钮 |

---

### 2. Chunk 预览

```
GET /tasks/{task_id}/chunks?page=1&limit=20
```

```json
{
  "code": 200,
  "task_id": "uuid",
  "total": 128,
  "page": 1,
  "limit": 20,
  "items": [
    {
      "index": 0,
      "text": "第一章 产品概述……",
      "metadata": { "page": 1, "source": "产品手册.pdf", "char_count": 512 }
    }
  ]
}
```

---

### 3. 任务列表

```
GET /tasks?limit=50&offset=0
```

```json
{
  "code": 200,
  "total": 3,
  "items": [
    {
      "task_id": "uuid",
      "file_name": "产品手册.pdf",
      "file_size": 2048000,
      "file_ext": "pdf",
      "status": "completed",
      "done_list": ["upload_file", "pdf_to_md"],
      "chunk_count": 128,
      "embedding_count": 128,
      "created_at": "2026-06-12T10:30:00"
    }
  ]
}
```

---

### 4. 删除任务

```
DELETE /tasks/{task_id}
```

```json
{
  "code": 200,
  "message": "任务已删除",
  "task_id": "uuid",
  "deleted": true
}
```
