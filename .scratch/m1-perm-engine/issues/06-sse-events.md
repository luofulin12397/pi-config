# 06: SSE 管线事件流

**What to build:** 查询图各节点向 SSE 会话推送结构化事件，线上化 frontend-demo 的管线步骤条（协议见 docs/api-contract.md §0）：`step`（六步：FAQ匹配/上下文/检索/鉴权/组装/生成；状态 running/done/skipped + detail）、`delta`（流式增量）、`refs`（引用列表 + 拦截数）、`done`（来源/耗时/token）。FAQ 命中时中间步骤标记 skipped。

**Blocked by:** None（refs 的 deniedCount 字段完整联调依赖 05）

**Status:** resolved

- [x] SSE 会话按序观察到六步 step 事件；语义缓存命中时后续步骤标记 skipped（FAQ 缓存属 M3，届时复用同一 skipped 机制）
- [x] delta 增量拼接与最终答案文本一致
- [x] refs 事件含引用与拦截数；done 含来源（rag/semantic-cache/denied/no-result）/耗时/token
- [x] 事件字段与契约 §0 一致（key/status/detail），可直接驱动 demo 步骤条


## Comments

- 新增 pipeline_events.py（shared 层）：六步映射 NODE_TO_STEP + emit_step/emit_skipped/emit_refs/emit_done
- 接入点：node_query_cache(faq)、node_history_compress(context)、node_rrf(search)、node_perm_filter(auth)、node_answer_output(compose/generate/refs)
- SSEEvent 扩展 STEP/REFS/DONE；invoke_query_graph 推 done（source/latency/tokens 估算）
- 联调修复两个 SSE 基础设施问题：①/query 流式受理先建队列+invoke 幂等创建（消除订阅/提问竞态）②sse_generator 队列不存在时等待 10s 而非立即断开（支持前端先订阅后提问）
- 验证：scripts/test_m1_sse.py 9/9（六步序列/delta 拼接一致/refs/done/缓存命中 skipped）
