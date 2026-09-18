"""
四维数据权限判定引擎单元测试（纯函数，不依赖 MongoDB）。
运行方式（项目根目录）:
    python3 scripts/test_perm_engine.py
覆盖 M1-01 验收：四维 OR 判定各分支 + 默认拒绝 + 旧格式（allowed_roles）兼容映射。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.infra.security.perm_engine import has_access, normalize_perms  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {name}")


# 用户上下文：张三=业务部 u dept-biz / 赵六=管理层 u-mgmt / 李四=财务部 u-fin
U_BIZ = {"user_id": "u-biz", "department_id": "dept-biz", "role_ids": ["r_emp"]}
U_MGMT = {"user_id": "u-mgmt", "department_id": "dept-gm", "role_ids": ["r_mgmt"]}

# 1. 全局公开：任何用户放行
check("全局公开放行", has_access(U_BIZ, {"global": True}))
# 2. 部门维
check("部门命中放行", has_access(
    {"user_id": "u-hr", "department_id": "dept-hr", "role_ids": []},
    {"department_ids": ["dept-hr"]}))
check("部门不命中拒绝", not has_access(U_BIZ, {"department_ids": ["dept-hr"]}))
# 3. 角色维
check("角色命中放行", has_access(U_MGMT, {"role_ids": ["r_mgmt"]}))
check("角色不命中拒绝", not has_access(U_BIZ, {"role_ids": ["r_mgmt"]}))
# 4. 个人维
check("个人命中放行", has_access(U_BIZ, {"user_ids": ["u-biz"]}))
check("个人不命中拒绝", not has_access(U_MGMT, {"user_ids": ["u-biz"]}))
# 5. 多维并存：任一命中即放行
check("多维任一命中放行", has_access(U_BIZ, {"role_ids": ["r_mgmt"], "user_ids": ["u-biz"]}))
# 6. 默认拒绝：全空 / 空文档 / None / 无 user_ctx
check("全空默认拒绝", not has_access(U_BIZ, {"global": False, "department_ids": [], "role_ids": [], "user_ids": []}))
check("空文档默认拒绝", not has_access(U_BIZ, {}))
check("None 默认拒绝", not has_access(U_BIZ, None))
check("无用户上下文拒绝", not has_access(None, {"global": True}))  # 无上下文即使全局公开也不放行（登录态由上层强制）
# 7. 旧格式兼容：allowed_roles → 角色维
legacy_doc = {"file_title": "高管薪酬细则", "item_name": "薪酬", "allowed_roles": ["r_mgmt", "admin"]}
check("旧格式角色命中放行", has_access(U_MGMT, legacy_doc))
check("旧格式角色不命中拒绝", not has_access(U_BIZ, legacy_doc))
check("旧格式归一化形状", normalize_perms(legacy_doc) == {
    "global": False, "department_ids": [], "role_ids": ["r_mgmt", "admin"], "user_ids": []})
# 8. 嵌套 perms 文档归一化
check("嵌套 perms 归一化", normalize_perms({"perms": {"global": True}})["global"] is True)
# 9. 缺字段容错（用户上下文缺 role_ids）
check("缺 role_ids 容错", not has_access({"user_id": "u1", "department_id": "d1"}, {"role_ids": ["r1"]}))

print(f"PASS {PASS} / FAIL {FAIL}")
sys.exit(1 if FAIL else 0)
