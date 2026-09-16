---
last_updated: 2026-07-17
status: active
---
# ai_0119_rag - 实施计划
> 只记活跃迭代和待办。
---
## 进度总览
| 里程碑 | 状态 | 说明 |
|---|---|---|
| M1 | 进行中 | [首个目标] |
---
## 当前活跃：M1 四维权限引擎
**目标**：权限从角色单维升级为四维（全局/部门/角色/个人，OR 判定、默认拒绝），并贯通到问答管线（无权召回零泄露、明确受限提示）。工单：外层 `.scratch/m1-perm-engine/issues/`；契约：外层 `docs/api-contract.md` §8
**影响文件**：
- `app/infra/security/perm_engine.py`（新增，判引擎）
- `app/infra/persistence/permission_repository.py`（expand：按 knowledge_id 的四维读写）
- 问答管线访问控制服务（M1-05）
**验收**：
- [x] M1-01 四维模型 + OR 判定 + 旧格式兼容（scripts/test_perm_engine.py 17/17）
- [ ] M1-02 台账 / M1-03 权限配置接口 / M1-04 auth-me / M1-05 管线过滤 / M1-06 SSE 事件
---
## 待办 / Backlog
| 优先级 | 功能 | 说明 |
|---|---|---|
---
## 文档同步 TODO
- [ ] 更新 docs/conventions.md
