# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 角色常量与导入权限校验

 @dependency auth_repository

 @output ADMIN_ROLE / validate_import_allowed_roles
"""

from fastapi import HTTPException, status

from app.infra.persistence.auth_repository import auth_repository

ADMIN_ROLE = "admin"


def validate_import_allowed_roles(requested_roles: list[str], user_roles: list[str]) -> list[str]:
    """
    校验导入文档的 allowed_roles
    :param requested_roles: 请求写入的 allowed_roles
    :param user_roles: 当前用户角色列表
    :return: 合法的 allowed_roles 列表
    """
    if not requested_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="allowed_roles 不能为空",
        )

    known_codes = {row["code"] for row in auth_repository.list_roles()}
    invalid = [r for r in requested_roles if r not in known_codes]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的角色: {', '.join(invalid)}",
        )

    if ADMIN_ROLE in user_roles:
        return list(requested_roles)

    overreach = [r for r in requested_roles if r not in user_roles]
    if overreach:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"无权为文档分配以下角色: {', '.join(overreach)}",
        )

    return list(requested_roles)


# ==================== 功能权限（菜单 / 按钮）— M1-04 ====================
# 契约见 docs/api-contract.md；前端 demo 的菜单/按钮集合与此一致（frontend-demo js/mock-data.js）

MENUS = ["chat", "knowledge", "ops", "dashboard", "org"]

BUTTONS_BY_MENU = {
    "chat": ["ask"],
    "knowledge": ["import", "edit", "delete", "perm"],
    "ops": ["faq-publish", "cache-toggle", "gap-task"],
    "dashboard": [],
    "org": ["dept-manage", "user-manage", "role-manage", "model-config"],
}

ALL_BUTTONS = [b for key in MENUS for b in BUTTONS_BY_MENU[key]]

# 各内置角色的功能权限默认配置（seed / 迁移补齐用）
DEFAULT_ROLE_PERMS = {
    "admin": {"menus": MENUS, "buttons": ALL_BUTTONS},
    "common_user": {"menus": ["chat"], "buttons": ["ask"]},
    "engineer": {"menus": ["chat"], "buttons": ["ask"]},
    "operator": {"menus": ["chat"], "buttons": ["ask"]},
}


def aggregate_menus(role_codes: list[str]) -> list[str]:
    """多角色菜单权限并集；含 admin 角色视为全量。

    以 roles 集合配置为准（可变更），旧角色缺字段时回退 DEFAULT_ROLE_PERMS。
    """
    if ADMIN_ROLE in role_codes:
        return list(MENUS)
    menus = set()
    for row in auth_repository.list_roles():
        code = row.get("code")
        if code not in role_codes:
            continue
        configured = row.get("menus")
        if configured is None:
            configured = DEFAULT_ROLE_PERMS.get(code, {}).get("menus", [])
        menus.update(configured)
    return [m for m in MENUS if m in menus]


def aggregate_buttons(role_codes: list[str]) -> list[str]:
    """多角色按钮权限并集；含 admin 角色视为全量（DB 配置优先，静态默认兜底）。"""
    if ADMIN_ROLE in role_codes:
        return list(ALL_BUTTONS)
    buttons = set()
    for row in auth_repository.list_roles():
        code = row.get("code")
        if code not in role_codes:
            continue
        configured = row.get("buttons")
        if configured is None:
            configured = DEFAULT_ROLE_PERMS.get(code, {}).get("buttons", [])
        buttons.update(configured)
    return [b for b in ALL_BUTTONS if b in buttons]


def has_button(role_codes: list[str], button_key: str) -> bool:
    """按钮级功能权限判定（接口层 RBAC 用，与数据级四维权限分层）。"""
    return button_key in aggregate_buttons(role_codes)
