# 01: 问答审计落库 + 查询接口

**What to build:** 每轮问答完成后异步写入 qa_logs 审计记录（需求 2.9.8：会话/用户/时间/提问/放行/拦截列表/来源/token/耗时）；运营接口提供倒序查询。为 M3-02/03/04 提供数据地基。

**Blocked by:** None (can start immediately)

**Status:** claimed

- [x] qa_logs 集合 + 仓储（insert / 倒序查询）
- [x] 管线完成后落库（faq-cache/rag/denied/no-result 全来源覆盖，含 allowedIds/deniedIds）
- [x] GET /ops/audit/logs?limit= 倒序返回
