# 01: 四维权限数据模型与判定引擎

**What to build:** 权限存储从"角色单维"升级为"全局(global)/部门(department)/角色(role)/个人(user)"四维，权限主体从商品主体名扩展到知识单元；旧的 allowed_roles 记录兼容读取（等价映射为角色维）。提供全系统唯一的 OR 判定函数：满足任一已配置维度即放行；全部未配置时默认拒绝。判定形状（来自 frontend-demo 原型）：`perms = {global, departmentIds[], roleIds[], userIds[]}`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 旧格式（仅 allowed_roles）权限记录可读取并等价映射为角色维
- [ ] OR 判定单测覆盖：全局命中 / 部门命中 / 角色命中 / 个人命中 / 多维并存 / 全部未配置默认拒绝
- [ ] 判定函数被权限仓储与问答链路共同复用（单一权威实现，无第二份判定逻辑）
