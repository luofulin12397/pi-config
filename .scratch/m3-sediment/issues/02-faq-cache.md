# 02: FAQ 存储与缓存直出 + 前端运营页

**What to build:** FAQ 已发布库（faqs）与候选池（faq_candidates）；问答管线最前先匹配已发布 FAQ（向量相似≥阈值）命中即毫秒直出标准答案不进检索；运营接口：手动添加候选/审核发布/驳回/缓存启停/删除；控制台新增「沉淀与运营」页（审计/候选/已发布三个 tab）。

**Blocked by:** 01

**Status:** claimed

- [x] faq_repository（published + candidates + 发布/驳回/启停）
- [x] node_query_cache 内 FAQ 优先匹配（bge-m3 余弦 ≥0.85，命中 source=faq-cache 并 emit skipped 序列；实测同义句 0.916 命中、250ms 直出）
- [x] 接口：候选列表/手动添加/发布/驳回、已发布列表/缓存启停/删除（独立 /ops 前缀 router）
- [ ] 前端「沉淀与运营」页：审计日志 tab + FAQ 候选 tab + 已发布 tab（接口已就绪，页面下一票接入）


## Comments

- 附加修复：/query 响应补 source 字段（faq-cache/semantic-cache/rag/denied/no-result）；source 由管线写入 state 后端点读取（修复作用域 NameError）
- 前端页面移至下一票（与缺口 tab 一并实现，避免本票过大）
