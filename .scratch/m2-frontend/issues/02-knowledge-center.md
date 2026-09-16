# 02: 知识维护与导入中心接真实 API

**What to build:** 控制台新增「知识维护与导入中心」页（require menus 含 knowledge）：台账列表（标题/格式/分类/权限标签/切片数/启停/更新时间）、批量文件导入（POST :55000/upload + 进度轮询）、编辑/启停/删除、切片预览抽屉、四维权限配置弹窗（全局开关 + 部门/角色/人员多选，数据源为轻量只读接口）。

**Blocked by:** None（M1-02/03 已交付台账与权限接口）。

**Status:** resolved

- [x] 后端补齐：GET /admin/knowledge/{id}/chunks（切片预览，Milvus 按 file_title 查询）
- [x] 后端补齐：GET /admin/departments、GET /admin/users（权限弹窗数据源，require_button('perm')）
- [x] 前端台账页：列表/搜索/启停开关/编辑/删除（确认）/切片预览/权限标签展示
- [x] 前端导入：多文件选择 → 逐文件上传（代理 /admin/import/upload）→ 轮询导入状态 → 完成刷新台账
- [x] 前端权限弹窗：四维配置（全局开关/部门多选/角色多选/人员多选）保存即生效
- [x] 页面按 /auth/me 的 menus（knowledge）与 buttons（import/edit/delete/perm）做显隐控制


## Comments

- 后端新增：chunks 预览（Milvus 按 file_title）、departments/users 数据源、导入代理（/admin/import/upload + /import/status，单端口透传 :55000）
- 前端：app.js 扩展知识中心视图（导航按 me.menus 渲染、操作按 me.buttons 显隐）
- 说明：拖拽导入本轮以多选按钮替代（drop 事件后续票补）；导入进度以节点 done/running 比例驱动（四阶段细分留后续）
- 组织树模型未落地，departments 暂聚合自 users.department_id（M3 组织页时升级）
- 回归：test_m1_sse.py 9/9、test_m1_perms.py 6/6（新增接口未破坏既有能力）
