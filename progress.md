# Progress —— RAG 智库管理平台

> 会话日志。每会话追加一节，记录做了什么、验证结果、产出文件。

## 会话 1 · 2026-09-16

### 完成内容
1. **需求解读**：《知识管理平台.md》五大板块 + 验收标准拆解，识别验收关键路径 = 2.9.9 场景演示（二选一）
2. **现有代码库盘点**：ai_rag_knowbase-master（FastAPI 双服务 + LangGraph + Milvus/MongoDB）能力对照，结论：后端底子可复用 ~60%，前端为零，四维权限/FAQ 沉淀/看板需新建（详见 findings.md §2）
3. **前端交互 Demo 开发**（`frontend-demo/`，不做后端实现）：
   - 核心逻辑真实跑在前端：四维权限 OR 判定 / 检索→鉴权→生成管线（LangGraph 6 步模拟，UI 步骤条可视化）/ FAQ 缓存命中 / 缺口闭环转任务
   - 6 页面：登录（5 角色一键切换）/ AI 问答工作台（会话侧边栏、流式 Markdown、引用溯源卡片、权限缺失提示气泡）/ 知识导入中心（批量拖拽、四阶段进度、四维权限弹窗）/ 沉淀运营（FAQ 审核发布、缺口转任务、审计日志）/ 运营看板（6 KPI + 4 ECharts）/ 组织配置（部门树、用户、角色按钮级权限树、可调阈值）
   - 内置 7 步端到端演示剧本（覆盖需求 2.9.9 两场景）
4. **验证**：
   - `node --check` ×3 通过；http.server 资源 200
   - 核心逻辑 10 项冒烟断言全部通过（发现并修复 bigram 虚词稀释问题，见 task_plan.md 错误表）
   - 未验证项：无无头浏览器，未做渲染冒烟（风险低）
5. **规划文件初始化**：task_plan.md / findings.md / progress.md（本文件）

### 产出文件
- `frontend-demo/`（index.html + css/app.css + js/{mock-data,services,app}.js + vendor/）
- `task_plan.md`、`findings.md`、`progress.md`

### 遗留/下一步
- 阶段 3：API 契约清单（页面/动作 → 接口 → demo 函数 → 代码库落点）
- 阶段 4：迭代实施计划（M1 权限引擎改造 → M2 前端工程化 → M3 沉淀+看板 → M4 Word/TXT + 端到端演示）
- 待确认 4 项（findings.md §5），其中两级缓存优先级影响 M3 设计，建议先澄清

## 会话 2 · 2026-09-16

### 完成内容：环境迁移修正（用户确认当前为云服务器，pi-config 从另一台电脑复制而来）
1. **诊断**：pi-config/skills 中 49 个指向 `/mnt/c/Users/12926/.agents/skills/` 的符号链接在云服务器全部失效；全局 AGENTS.md 环境描述（Windows 11 + WSL2）也已过时；全局指令引用的 diagnosing-bugs/tdd/grill-with-docs/ask-matt 均在死链中
2. **技能恢复**（源头重建实体）：
   - 37 个 ← github.com/mattpocock/skills（含全局指令依赖的 4 个）
   - 9 个 ← github.com/vercel-labs/agent-skills（vercel-* 系列，目录名做了映射：如 vercel-react-best-practices ← react-best-practices）
   - 3 个无源头已删死链：archify / likec4-dsl / planning-with-files（英文版；如需可从原电脑 `/mnt/c/Users/12926/.agents/skills/` 找回）
   - 安装模式：pi-config/skills 实体（git 管理）+ /root/.pi/agent/skills 软链指向 pi-config（与 AGENTS.md 同模式）
3. **AGENTS.md 修正**（pi-config/AGENTS.md，.pi 软链自动生效）：环境行改为云服务器 Linux；PowerShell/Windows 备注改为“Windows 来源文件备注（条件适用）”
4. **验证**：两边 skills 目录死链数为 0；抽查 tdd/ask-matt SKILL.md 内容正常；已 commit 到 pi-config（59bbe05，未推送）
5. **未验证项**：新技能需下次会话启动时才会进入 available_skills 列表（本会话启动时已注入的列表不变）

### 产出/变更文件
- `/root/pi-config/`（commit 59bbe05：+450 文件 / -49 死链 / AGENTS.md）
- `/root/.pi/agent/skills/`（46 个软链重定向 + 3 个死链移除）

## 会话 3 · 2026-09-16

### 完成内容：运行 setup-matt-pocock-skills，为项目仓库配置工程技能
1. 项目根 `git init`（main 分支），首次提交 f209aeb（含需求文档 / frontend-demo / planning 三件套；`.gitignore` 排除 ai_rag_knowbase-master）
2. 写入 `AGENTS.md`（项目约定 + `## Agent skills` 块）
3. 写入 `docs/agents/`：issue-tracker（本地 markdown，`.scratch/<feature>/`）、triage-labels（默认 5 标签）、domain（单上下文，CONTEXT.md/ADR 惰性创建）
4. 生效范围：to-tickets/to-spec/triage 读写 `.scratch/`；grill-with-docs/domain-modeling 按 domain.md 约定消费领域文档

### 变更文件
- `AGENTS.md`、`docs/agents/{issue-tracker,triage-labels,domain}.md`、`.gitignore`（commit f209aeb）

## 会话 4 · 2026-09-16

### 完成内容：阶段 3 — API 契约清单
1. 盘点现有接口（auth_routes 7 个 / import_server 4 个 / query_server 6 个）与全部 persistence 仓储、查询图 11 节点
2. 产出 `docs/api-contract.md`：46 个接口 × 五列映射（页面动作 → 接口 → 出入参 → demo 函数 → 落点[复用/改造/新增]），含 SSE step 事件协议、新增数据模型 6 集合、M1-M4 里程碑映射
3. 关键发现：约 40% 接口可纯复用；核心改造点收敛为一处（node_access_control 召回后四维过滤）；管理 API 挂 :55001 不加第三服务
4. task_plan 阶段 3 → complete；findings §7 摘要
5. 验证：落点均核对过实际文件名与现有路由（grep 确认）；未验证项：接口行为未实际运行（属 M1+ 实施内容）

### 变更文件
- 新增 `docs/api-contract.md`；更新 task_plan.md / findings.md / progress.md
