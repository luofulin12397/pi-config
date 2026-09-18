# RAG 智库管理平台 — 项目指令

依据《知识管理平台.md》（需求 2.9）构建：四维数据权限鉴权、AI 鉴权检索问答、FAQ 沉淀闭环、运营看板的知识库管理平台。

## 目录结构

| 路径 | 说明 |
|---|---|
| `知识管理平台.md` | 需求文档（甲方原文，只读不改） |
| `frontend-demo/` | 纯前端交互 Demo：核心业务逻辑（四维权限判定/检索鉴权管线/FAQ 缓存/缺口闭环）真实跑在前端，数据为 mock。`js/services.js` 是逻辑规格，函数与将来后端模块一一对应 |
| `ai_rag_knowbase-master/` | 现有 RAG 后端（FastAPI + LangGraph + Milvus/MongoDB，双服务 :55000/:55001）。**改动它须遵守其内部 `AGENTS.md`**（WF1：>5 文件先更新其 docs/plan.md 等）；排除在本仓库 git 之外 |
| `task_plan.md` / `findings.md` / `progress.md` | 跨会话规划三件套（planning-with-files）：会话开始先读，阶段推进后更新 |
| `docs/agents/` | 工程技能配置（issue tracker / triage 标签 / 领域文档消费规则），由 setup-matt-pocock-skills 生成 |

## 约定

- 跨会话状态只认规划三件套；决策记录在 `task_plan.md` 关键决策表
- 任务分工双层记录：里程碑状态权威在 `task_plan.md`；进入某个 M 的实施后用 `to-tickets` 拆票到 `.scratch/`，票状态权威在 `.scratch/`（`progress.md` 只引用票号不复制内容）
- `frontend-demo` 验证方式：`node --check js/*.js` + node 冒烟断言（stub window 后直接跑 services）
- 需求要点、差距分析、demo↔后端模块映射见 `findings.md`，不要重复分析
- 原则沿用全局：按痛渐进、外科手术式改动、完成前运行相称的验证
- 架构即代码（LikeC4）：`architecture/` 描述全平台（角色/双服务/存储/外部依赖）；接口契约（api-contract.md）或服务组件变更时同步更新，`npm run format:check` 验证。写 `.c4` 前先加载 skill `likec4-dsl`（`.pi/skills/`）
- 架构查询 MCP：`npm run mcp` 把架构模型暴露给 Agent，端点 `http://127.0.0.1:33335/mcp`，只读查询勿改模型。客户端传输类型**必须选 streamable HTTP/HTTP**：选 SSE 会请求不存在的 `/sse` 并报 `-32000 Method not found`（部分中文客户端汉化为“未找到方法。”）；只支持 SSE/stdio 的客户端改用 stdio：`npx likec4 mcp`

## Agent skills

### Issue tracker

Issues 以本地 markdown 存放：`.scratch/<feature-slug>/`（spec.md + issues/NN-<slug>.md）。See `docs/agents/issue-tracker.md`.

### Triage labels

使用五个默认规范标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。See `docs/agents/triage-labels.md`.

### Domain docs

单上下文（single-context）：`CONTEXT.md` + `docs/adr/` 在仓库根，由领域建模技能按需惰性创建。See `docs/agents/domain.md`.
