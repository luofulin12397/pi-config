# Findings —— RAG 智库管理平台

> 持久化研究发现与规格结论。外部内容只写本文件，不写入 task_plan.md。

## 1. 需求要点（《知识管理平台.md》）

- **四维混合数据权限**：全局(global) / 部门(department) / 角色(role) / 个人(user)，OR 充分条件逻辑；**默认无任何公开权限（默认拒绝）**；权限规则需"即时生效并同步鉴权引擎缓存"
- **AI 鉴权检索时序**：提取用户身份/直属部门/角色集合 → 混合检索（向量+关键词）Top-K → 鉴权过滤 → 仅放行切片拼 Prompt；无权召回项必须提示"部分参考资料因权限受限无法展示"，严禁越权泄漏
- **FAQ 沉淀闭环**：历史提问语义去重聚类 → 频次达阈值生成候选 FAQ → 管理员审核/在线润色 → 发布并写入内存缓存 → 新提问优先命中缓存毫秒级直出
- **知识缺口闭环**：相似度低于置信度阈值或未命中 → 自动入缺口池 → 按频次聚合 → 一键转知识补全任务
- **运营看板**：PV/UV、知识单元总量、高频问题 TOP、热门知识 TOP、Token 消耗趋势、响应延时分布
- **审计输出（2.9.8）**：单次问答记录须含 会话ID/用户/提问/召回列表/**鉴权通过列表/鉴权拦截列表**/Token/耗时
- **验收（2.9.10）**：9 条；演示场景 2.9.9 二选一（薪酬隔离 或 退换货 FAQ 沉淀）

## 2. 现有代码库差距对照（ai_rag_knowbase-master）

技术栈：FastAPI 双服务（导入 :55000 / 问答 :55001）+ LangGraph + Milvus + MongoDB + MinIO + Redis(可选) + uv

| 能力 | 现状 | 结论 |
|------|------|------|
| JWT 登录/刷新/登出、RBAC 角色、bcrypt | 已有（app/infra/security/） | ✅ 复用 |
| 文档导入管线（MinerU PDF→MD→切片→BGE-M3→Milvus，LangGraph 7 节点） | 已有 | ✅ 复用，需加 Word/TXT 分支 |
| 混合检索（稠密+HyDE+Web+RRF+Rerank，11 节点）、SSE 流式、引用溯源 | 已有 | ✅ 复用 |
| 文档权限 | 仅 `allowed_roles` 单维（permission_repository.py） | ⚠️ 需扩展为四维模型 |
| 鉴权位置 | `node_access_control` 按"商品主体名"预过滤 | ⚠️ 语义不同，需改为召回后按知识单元过滤 |
| 前端 | **完全没有**（无 package.json） | ❌ 最大缺口 |
| FAQ 挖掘/审核/发布 | 无（qa_cache 是自动语义缓存，非审核 FAQ） | ❌ 新增 |
| 知识缺口池 | 无 | ❌ 新增 |
| 运营看板（PV/UV/Token/延时聚合） | 无（仅逐条日志） | ❌ 新增聚合服务 |
| 部门树/用户管理界面 | 无组织模型 | ❌ 新增 |
| Word/TXT 解析 | 仅 PDF/MD | ❌ 新增解析分支 |

## 3. Demo 服务函数 ↔ 后端模块映射（frontend-demo/js/services.js）

| demo 函数 | 对应将来后端 | 说明 |
|-----------|-------------|------|
| `PermCore.hasAccess` | 动态数据权限鉴权引擎 | 四维 OR 判定唯一权威实现，默认拒绝 |
| `searchChunks` | 混合检索 | bigram 覆盖率模拟；真实实现换 bge-m3 + BM25 融合；同知识最多取 2 片防霸榜 |
| `permFilter` | 鉴权过滤（检索后） | 返回 {allowed[], denied[]} 两组 |
| `runPipeline` | AI 问答引擎 | 模拟 LangGraph 6 步：faq→context→search→auth→compose→generate；三分支（正常/全拦截/未命中缺口） |
| `faqMatch` | FAQ 高速缓存 | bigram 相似 ≥ faqHitThreshold(0.5) 命中；真实实现为 FAQ 向量余弦 |
| `addGap`/`convertGap` | 缺口闭环 | 相似问题聚合频次；转任务即补文档入库 |
| `logQa`/`dashboard` | 日志采集与看板服务 | 逐条落库 + 实时聚合（7日Token趋势/高频问题TOP5/热门知识TOP5/延时5桶分布） |
| `publishFaq`/`toggleFaqCache` | FAQ 审核发布 | 发布即写缓存；cacheEnabled 可停用 |

## 4. Demo 关键实现细节（frontend-demo/）

- 文件：`index.html` + `css/app.css` + `js/{mock-data,services,app}.js` + `vendor/{vue,echarts}`（npmmirror 下载，离线可用）
- 预置账号：zhangsan(业务部员工/主演示) / lisi(财务部知识管理员) / wangwu(HR) / zhaoliu(管理层) / admin(系统管理员) / sunqi(客服) / zhouba(财务员工)
- 预置知识：差旅报销标准(全局) / 高管薪酬细则(人力部+管理层) / 考勤制度(全局) / 生鲜退换货(全局) / 客服话术(全局) / 供应商负面清单(**个人专属**=李四)
- 种子日志：近 7 日 ~200 条，含"生鲜退款"52 次（支撑 FAQ 候选频次）、26 次 FAQ 缓存命中、5 次薪酬拦截
- 可调参数（组织配置页实时生效）：confThreshold=0.25 / faqHitThreshold=0.5 / faqRecommendThreshold=10 / topK=4
- 🎬 端到端演示剧本 7 步内置在侧边栏

## 5. 待确认问题（实现前需与需求方/自定澄清）

1. **两级缓存优先级**：FAQ 缓存（审核后）vs 现有语义缓存 qa_cache（自动）——谁先匹配？失效策略是否共享？
2. **"直属部门"口径**：四维权限的部门维度是否只判直属部门，还是含上级部门（部门树向上冒泡）？
3. **拦截提示粒度**：普通用户是否应感知"存在相关文档"这一事实本身？（demo 采用需求场景一的文案："检测到相关制度文档，但您当前所属部门/角色无权查阅该内容"）
4. **多轮上下文对检索的影响**：历史压缩摘要是否参与向量检索（现有库 node_history_compress 已有摘要能力，需要定拼接口径）

## 6. 验证记录摘要

- `node --check`：mock-data.js / services.js / app.js 语法通过
- 核心逻辑冒烟 10 项断言全部通过（四维判定 6 分支、检索命中、无权拦截、缺口入池→转任务→再检索闭环、FAQ 发布后缓存直出、看板聚合）
- 未验证：无无头浏览器，未做真实渲染冒烟（风险低：纯静态资源 + 常规 Vue3 用法）
