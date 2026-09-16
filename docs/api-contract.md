# API 契约清单 — RAG 智库管理平台

> 阶段 3 产出。三方映射：**页面/交互动作 → HTTP 接口 → demo 服务函数（frontend-demo/js/services.js）→ 现有代码库落点**。
> 落点标注：`[复用]` 现有接口/模块直接用；`[改造]` 现有模块需修改；`[新增]` 全新模块。
> 需求锚点：《知识管理平台.md》2.9.3 页面 / 2.9.6 后端模块 / 2.9.8 审计输出。

## 0. 全局约定

- **服务拓扑**：沿用双服务。导入类挂 `:55000`（import_server）；问答与管理类挂 `:55001`（query_server + 新增 `admin_routes.py`），不引入第三个服务
- **认证**：JWT Bearer（现有 `infra/security/jwt_utils.py` + `deps.CurrentUser`）；SSE 沿用独立 sse-token（`/auth/sse-token`）
- **鉴权双层**：接口级 RBAC（角色 buttons，对应 demo `hasBtn`）拦 `/admin/*`、`/ops/*`；数据级四维过滤在问答管线内（对应 demo `permFilter`），见 §4
- **响应包**：`ApiResponse[T]{code, message, data}`（现有惯例）
- **SSE 事件协议**（demo `runPipeline` 步骤条的线上化，`[新增]` node 回调机制）：
  ```
  event: step  data: {"key":"faq|context|search|auth|compose|generate","status":"running|done|skipped","detail":"..."}
  event: delta data: {"text":"..."}                      # 流式增量
  event: refs  data: {"refs":[{kid,title,score,text}],"deniedCount":N}
  event: done  data: {"source":"faq-cache|rag|no-result","latency":ms,"tokens":N,"messageId":"..."}
  ```

## 1. 认证与会话

| 接口 | 页面动作 | 关键出入参 | demo 函数 | 落点 |
|---|---|---|---|---|
| POST /auth/login | 登录页一键登录 | username/password → accessToken, refreshToken | LoginView.login | `[复用]` auth_routes |
| POST /auth/refresh · /auth/logout | 会话续期/登出 | — | — | `[复用]` auth_routes |
| GET /auth/me | 导航菜单/按钮级权限渲染 | → user{id,name,departmentId,roleIds[],**menus[],buttons[]} | hasBtn/hasMenu | `[改造]` auth_routes：UserInfo 增加 menus+buttons 展开字段 |
| GET /auth/roles · /auth/sse-token · /auth/permissions | 角色列表 / SSE 令牌 / 文档权限 | — | — | `[复用]` auth_routes |

## 2. 组织与系统配置（需求：组织架构与系统配置页）

| 接口 | 页面动作 | 关键出入参 | demo 函数 | 落点 |
|---|---|---|---|---|
| GET /admin/departments | 部门树渲染 | → 树[{id,name,parentId}] | DeptTree | `[新增]` admin_routes + org_repository（departments 集合） |
| POST/PUT/DELETE /admin/departments[/{id}] | 保存/新增子部门/删除 | name, parentId；删除需校验无子部门无用户 | upsertDept/deleteDept | `[新增]` 同上 |
| GET /admin/users | 用户表 | → [{id,name,username,departmentId,roleIds[],enabled}] | — | `[新增]` admin_routes（复用 auth_repository 的用户集合） |
| POST/PUT /admin/users[/{id}] | 新增/编辑用户、启停 | name, username, departmentId, roleIds[], enabled | upsertUser | `[新增]` admin_routes |
| GET /admin/roles | 角色列表 + 权限树回显 | → [{id,name,menus[],buttons[]}] | — | `[改造]` auth_routes /roles：补 menus/buttons 字段（现仅角色名） |
| PUT /admin/roles/{id} | 角色→菜单/按钮勾选保存 | menus[], buttons[] | updateRole | `[新增]` admin_routes（roles 集合扩展） |
| GET/PUT /admin/settings | 模型服务配置 + 沉淀阈值 | apiBase/chatModel/embedModel/temperature/topK/**confThreshold/faqHitThreshold/faqRecommendThreshold** | DB.settings 读写 | `[新增]` admin_routes + settings_repository |

## 3. 知识维护与导入（需求：知识维护与导入中心）

| 接口 | 页面动作 | 关键出入参 | demo 函数 | 落点 |
|---|---|---|---|---|
| POST :55000/upload | 单文件上传 | multipart(file) → taskId | ImportDrawer.addFiles | `[复用]` import_server；`[改造]` LangGraph 导入图入口节点加 **Word/TXT 分支**（M4） |
| POST :55000/upload（多文件循环） | 批量/文件夹拖拽 | 前端并发多次调用即可 | addFiles | `[复用]` |
| GET :55000/status/{task_id} | 四阶段进度条 | → status/progress | ImportDrawer job | `[改造]` progress 细化为 清洗/分块/向量化/入库 四阶段百分比 |
| GET /admin/knowledge | 台账列表 | ?kw=&category= → [{id,title,format,category,perms,chunks,enabled,updatedAt}] | KnowledgeView.list | `[新增]` knowledge_repository（knowledge_units 集合；导入图完成时登记） |
| PUT /admin/knowledge/{id} | 编辑标题/分类/启停 | title?, category?, enabled? | updateKnowledge | `[新增]`（enabled=false 需同步 Milvus 过滤或删除） |
| DELETE /admin/knowledge/{id} | 删除知识单元 | — | deleteKnowledge | `[新增]` + `[改造]` milvus_gateway 按 kid 删除向量 |
| GET /admin/knowledge/{id}/chunks | 切片预览抽屉 | → [{id,text}] | chunksOf | `[新增]` milvus_gateway query by expr(kid) |
| **PUT /admin/knowledge/{id}/permissions** | 四维权限弹窗保存 | {global,departmentIds[],roleIds[],userIds[]} | setPerm | `[改造]` permission_repository：`allowed_roles` 单维 → 四维模型；保存后同步鉴权引擎缓存（需求 2.9.7 流程 4） |

## 4. AI 鉴权问答（需求：AI 智能问答工作台）★ 核心改造

| 接口 | 页面动作 | 关键出入参 | demo 函数 | 落点 |
|---|---|---|---|---|
| POST /query（非流式） | 问答提交 | {question, sessionId, historyRounds} | ChatView.send | `[复用]` query_server |
| GET /stream/{session_id}（SSE） | 流式输出+管线步骤条 | 事件协议见 §0 | runPipeline(msg.steps/msg.text) | `[改造]` query agent：`[新增]` node 级 SSE 事件回调 |
| —（管线内） | **FAQ 缓存匹配** | 相似度 ≥ faqHitThreshold → 直接返回 | faqMatch | `[新增]` faq_repository 查询节点，置于 `node_query_cache` **之前**（两级缓存优先级见决策 D3，待产品确认） |
| —（管线内） | **四维鉴权过滤** | 检索后：permFilter(user, candidates) → {allowed, denied} | permFilter | `[改造]` node_access_control：从"商品主体名预过滤"改为"召回后按知识单元四维过滤"；denied 只进审计不进 Prompt |
| —（管线内） | **未命中 → 缺口** | topScore < confThreshold → 写缺口池 | addGap | `[改造]` 答案节点 + `[新增]` gap_repository |
| GET /chat/sessions · POST · DELETE /chat/sessions/{id} | 会话侧边栏 | → [{id,title,createdAt}] | sessions 管理 | `[改造]` history_repository：会话与消息两级（现有 chat_message 平铺，需聚合出会话） |
| GET /chat/sessions/{id}/messages | 会话消息回放 | → 消息含 refs/deniedCount/meta | messages 渲染 | `[改造]` 同上：落库时保存 refs/denied 元数据 |
| GET /suggestions?q= | 联想提问 | → string[]（FAQ 问题 + 热词前缀/包含匹配） | suggestions | `[改造]` query_server 现有接口：数据源加入已发布 FAQ |

## 5. 知识沉淀与运营（需求：FAQ 挖掘审核 / 缺口清单 / 审计）

| 接口 | 页面动作 | 关键出入参 | demo 函数 | 落点 |
|---|---|---|---|---|
| GET /ops/faq/candidates | 候选 FAQ 列表 | → [{id,questions[],freq,relatedKnowledgeIds[],draftAnswer,confidence,status}] | OpsView.candidates | `[新增]` 沉淀服务（定时任务聚类 qa_logs，freq ≥ faqRecommendThreshold 生成候选） |
| PUT /ops/faq/candidates/{id} | 在线润色答案 | draftAnswer | 编辑 textarea | `[新增]` 同上 |
| POST /ops/faq/candidates/{id}/publish | 审核发布 → 写入缓存 | {question, answer} | publishFaq | `[新增]` faq_repository + 缓存注入（需求 2.9.4：审核后打标上线同步内存缓存） |
| POST /ops/faq/candidates/{id}/reject | 驳回 | — | rejectFaq | `[新增]` |
| GET /ops/faqs | 已发布 FAQ 列表 | → [{id,question,answer,cacheEnabled,hitCount,publishedAt}] | OpsView.published | `[新增]` faq_repository |
| PUT /ops/faqs/{id}/cache | 缓存启停开关 | {enabled} | toggleFaqCache | `[新增]` |
| DELETE /ops/faqs/{id} | 删除 FAQ | — | — | `[新增]` |
| GET /ops/gaps | 知识缺口清单 | → [{id,question,department,freq,maxScore,suggestedCategory,status}] | OpsView.gaps | `[新增]` gap_repository（管线 addGap 聚合写入） |
| POST /ops/gaps/{id}/convert | 一键转知识补全任务 | {title, category, global, note} → 创建知识单元并触发导入管线 | convertGap | `[新增]` + `[复用]` :55000 导入图 |
| GET /ops/audit/logs | 问答审计日志（admin） | ?limit=50 → [{ts,uid,q,source,allowedIds[],deniedIds[],tokens,latency}]（需求 2.9.8 完整字段） | OpsView.auditLogs | `[新增]` audit_repository（管线 done 时异步落库） |

## 6. 运营看板（需求：运营看板与数据大盘）

| 接口 | 页面动作 | 关键出入参 | demo 函数 | 落点 |
|---|---|---|---|---|
| GET /admin/dashboard/summary | 6 张 KPI 卡 | → {pv,uv,kbTotal,faqHitRate,tokenToday,avgLatency} | dashboard() | `[新增]` 日志聚合服务（Mongo aggregation on qa_logs） |
| GET /admin/dashboard/trends?days=7 | Token/PV 折线 | → {days[],tokens[],pv[]} | dayTokens/dayPv | `[新增]` 同上 |
| GET /admin/dashboard/top-questions | 高频问题 TOP5 | → [{q,n}]（真实实现按聚类簇聚合） | topQuestions | `[新增]` 同上 |
| GET /admin/dashboard/top-knowledge | 热门知识 TOP5 | → [{title,n}]（按 allowedIds 引用计数） | topKnowledge | `[新增]` 同上 |
| GET /admin/dashboard/latency-distribution | 延时分布 | → [{label,n}]（5 桶，仅 RAG 来源） | latencyDist | `[新增]` 同上 |

## 7. 新增数据模型汇总

| 集合 | 关键字段 | 来源 |
|---|---|---|
| `departments` / `roles`（扩展） | parentId 树 / menus[],buttons[] | 组织配置 |
| `knowledge_units` | id,title,format,category,enabled,perms{global,departmentIds,roleIds,userIds},updatedAt | 台账（导入图完成时登记） |
| `faqs` / `faq_candidates` | question,answer,cacheEnabled,hitCount / questions[],freq,confidence,status | 沉淀 |
| `gaps` | question,department,freq,maxScore,suggestedCategory,status | 缺口闭环 |
| `qa_logs`（审计） | sessionId,userId,ts,question,recallIds[],allowedIds[],deniedIds[],tokens,latency,source | 需求 2.9.8 |
| `settings` | 模型参数 + 三个阈值 | 系统配置 |

## 8. 里程碑映射

| 里程碑 | 涉及接口/改造 |
|---|---|
| M1 四维权限引擎 | §1 /auth/me 改造；§3 permissions 接口 + permission_repository 四维化；§4 node_access_control 改造 + SSE step 事件 |
| M2 前端工程化 | 全部接口的前端接入（demo → Vue3 工程化） |
| M3 沉淀 + 看板 | §5 全部 + §6 全部 + §4 FAQ 缓存节点 |
| M4 Word/TXT + 端到端演示 | §3 upload 改造；场景演示联调 |
