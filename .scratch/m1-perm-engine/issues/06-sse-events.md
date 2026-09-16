# 06: SSE 管线事件流

**What to build:** 查询图各节点向 SSE 会话推送结构化事件，线上化 frontend-demo 的管线步骤条（协议见 docs/api-contract.md §0）：`step`（六步：FAQ匹配/上下文/检索/鉴权/组装/生成；状态 running/done/skipped + detail）、`delta`（流式增量）、`refs`（引用列表 + 拦截数）、`done`（来源/耗时/token）。FAQ 命中时中间步骤标记 skipped。

**Blocked by:** None（refs 的 deniedCount 字段完整联调依赖 05）

**Status:** ready-for-agent

- [ ] SSE 会话按序观察到六步 step 事件；FAQ 缓存命中时检索/鉴权/组装/生成标记 skipped
- [ ] delta 增量拼接与最终答案文本一致
- [ ] refs 事件含引用（标题/得分/摘要）与拦截数；done 含来源/耗时/token
- [ ] 该协议可直接驱动 demo 步骤条（对照 docs/api-contract.md §0）
