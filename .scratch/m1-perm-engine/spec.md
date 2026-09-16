# M1: 四维权限引擎 — Spec

目标：权限从"角色单维"升级为"全局/部门/角色/个人四维 OR（默认拒绝）"，并贯通到问答管线：无权召回项零泄露、明确提示。

详细契约：
- 接口定义：`docs/api-contract.md` §1 /auth/me、§3 permissions、§4 管线改造、§0 SSE 事件协议
- 里程碑映射：`docs/api-contract.md` §8 M1
- 逻辑参照：`frontend-demo/js/services.js`（PermCore.hasAccess / permFilter / runPipeline 分支 B）
- 需求锚点：《知识管理平台.md》2.9.4、2.9.10（鉴权相关验收条目）、2.9.9 场景一

完成演示路径：管理员配置《高管薪酬细则》仅人力部+管理层 → 张三问薪酬 → 受限提示不泄内容 → 赵六（管理层）问同一问题 → 正常回答。
