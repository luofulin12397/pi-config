# 04: /auth/me 菜单按钮权限展开

**What to build:** 登录态下 GET /auth/me 除用户信息外，返回该用户角色集合展开出的可用菜单清单与按钮权限清单，前端（含 M2 工程化前端与 demo）据此做菜单显隐与按钮级鉴权，不再硬编码角色名判断。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 不同角色登录，me 返回的 menus/buttons 与该角色的权限配置一致
- [ ] 管理员调整角色按钮权限后，该角色用户重新登录可见变化
