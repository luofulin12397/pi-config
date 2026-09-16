# 01: 控制台 SPA——登录 + AI 问答工作台接真实后端

**What to build:** 用户在浏览器打开 `http://<host>:55001/console/`，用真实账号（admin/zhangsan 等）登录后进入问答工作台：提问走真实 RAG 管线，页面实时展示六步管线步骤条（SSE）、流式答案、引用溯源与权限受限提示——即需求 2.9.3「AI 智能问答工作台」的最小可用版，并把 frontend-demo 中验证过的交互逻辑换成真实 API。

**Blocked by:** None（M1 已交付全部后端能力）。

**Status:** resolved

- [x] 由 query_server 静态挂载（/console/，单端口无 CORS），Vue3 本地 vendor
- [x] 登录页：POST /auth/login → token 存储 → GET /auth/me 展示用户与角色
- [x] 流式问答：订阅 /stream/{sid}（sse-token）+ POST /query(is_stream)，渲染 step 六步/流式 delta/refs/done
- [x] 受限提示与引用溯源卡片正确渲染（denied_ids→受限气泡；citations→溯源卡）
- [x] 未登录访问控制台重定向登录页（401 → 清 token → 登录视图）

## Comments

- 部署：query_server 挂载 console/ 静态目录，访问 http://<host>:55001/console/
- 前端数据流 E2E：zhangsan sse-token 订阅 → 六步 done 序列完整 → 234 片 delta → refs 1 条 → done(rag, 31s)
- 范围说明：本票为问答工作台最小可用版；知识中心/沉淀/看板/组织页在后续票接入（后端接口已在 docs/api-contract.md 就绪）
