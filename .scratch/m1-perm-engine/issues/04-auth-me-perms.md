# 04: /auth/me 菜单按钮权限展开

**What to build:** 登录态下 GET /auth/me 除用户信息外，返回该用户角色集合展开出的可用菜单清单与按钮权限清单，前端（含 M2 工程化前端与 demo）据此做菜单显隐与按钮级鉴权，不再硬编码角色名判断。

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] 不同角色登录，me 返回的 menus/buttons 与该角色的权限配置一致（admin 全量 / common_user 仅 chat+ask 实测）
- [x] 管理员调整角色按钮权限后，重新登录可见变化（common_user ask → ask+edit 实测）


## Comments

- 实现：role_utils 增加菜单/按钮常量与聚合函数（aggregate_menus/buttons/has_button，DB 配置优先、静态默认兜底、admin 直通全量）；UserInfo 增加 menus/buttons；deps 增加 require_button(key) 依赖工厂供各管理接口复用
- roles 集合扩展 menus/buttons 字段，seed_auth 迁移补齐存量角色
- 注意：user_roles.user_id 必须存 ObjectId（list_user_role_codes 按 ObjectId 匹配，字符串存入会导致角色聚合为空）
