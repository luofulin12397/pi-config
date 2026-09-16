# 05: 问答管线召回后四维过滤 + 受限提示

**What to build:** 混合检索产出候选后，调用统一判定引擎做四维鉴权分流：仅放行切片拼入提示词；召回中含无权知识单元时，回答明确提示"检测到相关制度文档，但您当前所属部门/角色无权查阅该内容"，不泄露任何受限内容；放行/拦截列表进入答案元数据。问答强制校验登录态。改造位置：现有"访问控制服务"（由商品主体名预过滤改为召回后按知识单元过滤）。

**Blocked by:** 01, 03

**Status:** resolved

- [x] 知识单元仅部门 A 可见：部门 A 用户问答正常引用；部门 B 用户命中该单元时得到受限提示，答案与引用零泄露
- [x] 受限场景下答案元数据含拦截列表（响应 denied_ids），提示词组装不含被拦截切片（node_perm_filter 先分流）
- [x] 未登录调用问答被拒绝（401 实测）
- [x] 可按需求 2.9.9 场景一完成端到端演示（scripts/test_m1_scenario.py 10/10）


## Comments

- 新增 node_perm_filter（rerank 后、组装前）：file_title→kid 稳定映射 → 批量查四维权限 → has_access 分流；仅放行切片进 reranked_docs
- 全部拦截时短路：answer=受限提示文案 + skip_cache（受限答案不写语义缓存，避免其他用户命中）
- 旧的前置主体角色过滤（access_validate 角色交集）已移除：主体名仅限定检索范围，数据权限统一由召回后四维判定（导入 allowed_roles 不再决定可见性）
- 部门链路：users.department_id → CurrentUser → query state；响应新增 allowed_ids/denied_ids（审计口径，需求 2.9.8）
- 顺带优雅化：三路检索全空时 rrf 不再抛 500，返回"未找到相关内容"提示
- 验证：scripts/test_m1_scenario.py 10/10；后端 commit 见 M1-05 提交
