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

### 阶段 4 启动：M1 拆票
- `to-tickets` 拆为 6 张垂直切片票，发布至 `.scratch/m1-perm-engine/issues/`（01 权限模型 / 02 台账 / 03 权限配置 / 04 auth-me / 05 管线过滤★ / 06 SSE 事件流），全部 Status: ready-for-agent
- Frontier：01、02、04、06 可立即并行开工；05 blocked by 01+03

### 会话 4 续：M1-01 工单实施完成
- 认领并完成 `.scratch/m1-perm-engine/issues/01-perm-model.md`：新增 perm_engine 判定引擎（纯函数）+ permission_repository expand（按 knowledge_id 四维读写，旧格式兼容）
- 验证：scripts/test_perm_engine.py 17/17 通过（OR 分支/默认拒绝/旧格式映射）；Mongo 集成验证留待服务联调
- 后端仓库 git init：9748ebd 基线 → 2edad68 M1-01（.env/doc/logs/output 已 ignore，.env 含密钥未入库）
- 票 01 → resolved；task_plan M1 进度同步

### 会话 4 续：M1-02 代码交付（待集成验证）
- knowledge_repository + 导入图登记 + 双检索停用过滤 + admin_routes（:55001 require_admin）；后端 commit 448d02c
- 已验证：py_compile 9 文件、perm_engine 回归 17/17；接口集成验证需 Mongo+Milvus+LLM 环境（阻塞点：.env API key 失效需用户提供）

### 会话 4 续：联调环境搭建 + M1-01/02 集成验收通过
1. **环境**：安装 docker+compose；deploy/docker-compose.yml 起 mongo/etcd/minio/milvus（配 registry mirror）；.venv 装轻量依赖子集；.env 指向 DeepSeek（chat）+ 硅基流动（embedding/rerank API）
2. **模型层 API 化**：embedding（dense API + 本地 sparse 哈希近似）、reranker（/rerank 适配器，形状兼容）——摆脱本地 torch/模型权重
3. **联调发现并修复 3 个缺陷**（ISS-001/002/003）+ 2 项一致性/韧性改造（缓存失效、主体确认回退）
4. **验收**：test_m1_ledger.py 9/9；票 01 Mongo 集成补验通过、票 02 → resolved（后端 commit 448d02c + 5b3bcdd）
5. 遗留：三路检索全空时 rrf 抛 ValueError 返回 500（应优雅返回"未找到"）——记入 M1-05 重构范围；停用问答依赖过滤后三路空的表现需在 M1-05 一并优雅化

### 会话 4 续：M1-04 完成
- role_utils 功能权限聚合（aggregate_menus/buttons/has_button，DB 优先）+ UserInfo 展开 + require_button 依赖工厂
- 验证：admin 全量 / common_user 最小权限 / 角色按钮变更后重新登录实时反映，全部通过

### 会话 4 续：M1-03 完成
- GET/PUT /admin/knowledge/{id}/permissions（require_button('perm')）+ 台账 perms/permLabels
- 关键设计：权限保存即清当前版本语义缓存（收回权限后缓存旧答案不得返回，防泄漏）
- 验证：test_m1_perms.py 7/7（含 403 按钮级拒绝、清空默认拒绝）

### 会话 4 续：M1-05 核心票完成（场景一端到端验收 10/10）
- 新增 node_perm_filter（rerank 后召回过滤）+ 旧前置角色过滤移除 + 部门链路（users→CurrentUser→state）+ 响应 allowed_ids/denied_ids + rrf 空结果优雅化 + 受限答案跳过缓存
- 验收：test_m1_scenario.py 10/10（2.9.9 场景一：张三差旅正常/薪酬受限零泄露/赵六正常/未登录 401）

### 会话 4 续：M1-06 完成，M1 里程碑收官
- pipeline_events（六步映射+emit_*）+ SSEEvent 扩展 STEP/REFS/DONE + invoke_query_graph done 事件
- 联调修复 SSE 基础设施两个问题：流式受理先建队列消除竞态；sse_generator 等待队列而非立即断开（支持先订阅后提问）
- 验收：test_m1_sse.py 9/9；M1 全部六票 resolved

### 会话 4 续：M2-01 完成——控制台 SPA 接真实后端
- ai_rag_knowbase-master/console/ 静态 SPA（Vue3 vendor + ES modules，无构建链），query_server 挂载 /console/（单端口 55001）
- 登录（/auth/login + /auth/me 菜单按钮展开）+ 流式问答工作台（sse-token 订阅 → 六步步骤条 → 流式 delta → 引用/受限 → done meta）
- 验证：JS 语法检查 + 前端数据流 E2E（六步 done 序列、234 片 delta、refs/done）
- 用户可浏览器访问 http://<host>:55001/console/ 体验真实系统

### 会话 4 续：M2-02 完成——知识维护与导入中心
- 后端：chunks 预览接口、departments/users 数据源、导入代理（单端口）
- 前端：知识中心视图（台账/导入/编辑/删除/启停/切片预览/四维权限弹窗，menus/buttons 驱动显隐）
- 回归：SSE 9/9、权限 6/6

### 会话 4 收尾状态（当日暂停点）
- 已交付：M1 全部 6 票 resolved（后端 9e0e1a8）；M2-01 控制台 SPA、M2-02 知识中心（8e2c3ff、324b1d7 + 兼容性修复）
- 遗留待确认：①用户浏览器白屏问题——已修可选链兼容性 + 页面错误捕获，**待用户 Ctrl+F5 刷新确认**；若仍白屏，页面顶部会显示红色 JS 错误，让用户复制错误信息
- 待办提醒：①两个 API key（DeepSeek/硅基流动）已在对话中暴露，建议轮换后更新 .env；②services.js（frontend-demo）与 console（真实前端）并存，demo 保留作为交互原型参考
- 明日继续点：确认控制台可访问 → 按需调整交互 → M2 剩余（知识中心细节打磨/导入拖拽）或直接 M3（沉淀+看板，后端服务需新建）

### 会话 4 续：M3-01/02 完成
- 审计落库（qa_logs，全来源覆盖含 allowed/denied 列表）+ GET /ops/audit/logs
- FAQ 全链路：faqs/faq_candidates 集合、手动建候选、审核发布（question 向量预计算）、管线 FAQ 优先匹配（余弦 0.85 阈值，实测 0.916 命中 250ms 直出）、hitCount
- 修复：/query 响应补 source 字段 + audit_source 作用域 NameError
- 接口规范：ops 接口独立 /ops 前缀 router（契约路径对齐）
- 验证：scripts/test_m3_sediment.py 8/8（首轮 RAG→建候选→发布→同义直出→hitCount→审计双来源）

### 暂停点（等用户体验后继续）
- **下一步**：M3-03 挖掘服务+缺口池 → M3-04 看板 → 前端「沉淀与运营」页（审计/FAQ 候选/已发布三 tab，接口已全部就绪）+ 看板页
- 用户正在浏览器体验控制台（http://<host>:55001/console/），体验中提出的交互调整在继续时一并收集处理
- 服务均在运行：docker 4 容器 + 双服务（55000/55001）；控制台入口 /console/

### 会话 4 续：M3-03/04 完成，M3 里程碑收官
- 挖掘服务（bge-m3 向量聚类贪心归簇，频次≥10 自动生成候选）+ 缺口池（no-result 聚合 + 转补全任务闭环）
- 看板聚合端点 /admin/dashboard/overview + 前端看板页（6 KPI + 趋势/TOP 问题/TOP 知识/延时分布 4 图）
- 前端沉淀与运营页（审计/候选/已发布/缺口 4 tab + 挖掘按钮）
- 演示数据：scripts/seed_qalogs.py（近 7 日日志注入）
- 验证：test_m3_sediment.py 12/12（含挖掘生成候选→发布→直出→缺口→转任务→看板全链路）

### 会话 4 续：M4 完成——全部里程碑收官
- text_convert_service（TXT 编码回退直读 / DOCX python-docx 标题映射）+ entry_service 分支（转 MD 复用链路）
- 验证：test_m4_formats.py 4/4（docx 切 2 片 / txt 切 1 片 / 默认拒绝 / 配 global 后可检索）
- 至此需求 2.9 核心能力全部落地：四维权限问答（场景一 10/10）、FAQ 沉淀直出（场景二链路 12/12）、知识中心、审计、看板、多格式导入

### 会话 4 续：部署文档 + 场景二演示脚本 + M2 打磨
- docs/deployment.md：快速启动/账号/演示路径/验收脚本清单/常见问题
- scripts/demo_scenario2.py：场景二一键演示（导入→高频提问→挖掘→发布→134ms 直出→缺口闭环），已跑通
- M2 打磨：知识中心拖拽导入 + 导入进度映射四阶段（节点名→清洗/分块/向量化/入库）
- 遗留：会话侧栏（GET /history 分组，下一票）

### 会话 4 续：M2-03/04 完成（会话侧栏 + 组织与系统配置页）
- 会话侧栏：/history 按 session 分组、点击加载、新会话
- 组织页：用户 CRUD（禁用=login 403）、角色 menus/buttons 编辑、模型配置只读卡
- 修复：list_console_users 字段映射丢弃问题；组织 E2E 7/7

### 会话 4 续：Playwright 冒烟测试接入 + 前端三连修
- 服务器安装 Playwright（chromium headless），新增 scripts/console_smoke.py：登录 → 遍历 5 页 → 收集 console 错误 → 截图
- 三连修：①诊断脚本块缺 `</script>` 闭合 → 每次页面加载 SyntaxError（红条常驻根因）②「组织与系统配置」入口仍为 disabled 占位 ③saveCandidate 回调 this 未绑定
- 冒烟结果：登录/知识中心(11行)/沉淀(4tab)/看板(6KPI)/组织(表格)全部渲染，页面 JS 错误 0
- 说明：用户看到的红条 = ①的错误（功能不受影响），现已根治

### 会话 5：LikeC4 架构即代码落地（`architecture/`）
- 建立 LikeC4 工作区（likec4 1.59.3 + npm scripts：dev/build/build:single/export:png/format/mcp），VS Code 扩展与 MCP 双通道可查
- 模型从「服务级 24 元素」细化到「代码模块级」：**108 元素 / 75 关系 / 21 视图**
  - A 后端模块级：按 `app/` 真实目录树建模（api 入口 5 / process 编排 21（含 19 个 LangGraph 节点）/ rag 业务 28 / infra 15 / shared 7）
  - B 节点级：导入图 7 节点、问答图 **12 节点**（多出 M1 新增的 `node_perm_filter`，此前图上没有）
  - C 开发导航：每元素带 `metadata.path`（仓库相对路径）+ `link` 源码链接 + 里程碑标签（M1-M4 / reuse / added / refactor）
  - D 部署视图：compose 只跑 4 个数据服务，两个 FastAPI 进程为宿主机 uv 进程（此前架构未体现）
- 核实修正的依赖事实：`node_perm_filter` 直连 `perm_engine.has_access` + `permission_repository` + `knowledge_repository`（不经 `access_control_service`，后者是遗留壳）；审计落库在 `query_server.py`
- 验证：`likec4 format` 0 错误；21 个视图经 headless Chromium 逐个渲染 0 报错；单文件 HTML 4.1MB（file:// 下 3 视图实测通过）
- 语法坑（已写进 .c4 注释）：1.59.3 **不支持 `**` / `_` 通配**（skill 文档是 main 分支新语法），里程碑视图用显式 FQN 清单、部署视图用 `element.*` 逐层展开；部署节点属性须写在 `instanceOf` 之前
- 遗留：里程碑视图为显式清单，新增带标签元素后需同步补录

### 会话 5 续：交付用容器化部署配置（在 ai_rag_knowbase-master 内，独立 git 提交 4dce62e）
- `Dockerfile`（python-slim + uv，双服务共用）+ `.dockerignore`（排除 .env/output/logs/doc/models/.venv）
- `deploy/requirements.deploy.txt`：由 `scripts/gen_deploy_requirements.py` 从 uv.lock 做依赖图可达性分析生成（111 / 234 包），剔除 app/ 零导入的 torch/CUDA 等 → 镜像 **815 MB**
- `deploy/docker-compose.full.yml`：4 数据服务 + 2 应用服务；容器内网络改服务名；`PUBLIC_HOST` 解决 MinIO 图片地址必须浏览器可达的问题
- 两份 env 模板（应用级 `.env` / compose 插值级 `deploy/.env`）+ `scripts/package_release.sh`（来源包 1.4 MB，含敏感内容硬校验）
- 实测：compose config 通过、镜像构建 815 MB、容器内双服务导入（18/52 路由）、`/health` 与 `/console/` 均 200
- 踩坑记录：`uv sync --no-install-package` 不剔除传递依赖；打包脚本排除模式前缀与 SIGPIPE 导致校验静默失效；compose `${}` 不读仓库根 .env；Windows 生成的锁文件含平台专属包
- 文档：外层 `docs/deployment.md` 新增第七节（容器化交付流程），并说明手写安装列表以生成清单为准
