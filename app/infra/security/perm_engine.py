# -*- coding: utf-8 -*-
"""
四维数据权限判定引擎（单一权威实现）。

需求锚点：《知识管理平台.md》2.9.4
- 默认状态下知识单元无任何公开访问权限（默认拒绝）
- 四类权限实体：全局(global) / 部门(department) / 角色(role) / 个人(user)
- 充分条件（OR 逻辑）：满足任意一个已配置权限实体即可访问

设计约束：
- 纯函数，不依赖数据库；仓储层负责读取记录并经 normalize_perms 归一化
- 全系统（权限配置接口、问答管线、后台任务）一律复用本模块判定，禁止散落第二份判定逻辑
- 原型参照：frontend-demo/js/services.js 的 PermCore.hasAccess

四维 perms 存储形状（内部与 MongoDB 统一 snake_case，API 层负责 camelCase 转换）::

    perms = {
        "global": bool,
        "department_ids": [...],
        "role_ids": [...],
        "user_ids": [...],
    }

用户判定上下文::

    user_ctx = {
        "user_id": str,
        "department_id": str,      # 直属部门
        "role_ids": [str, ...],
    }
"""
from __future__ import annotations

_NEW_SHAPE_KEYS = ("global", "department_ids", "role_ids", "user_ids")


def _empty_perms() -> dict:
    return {"global": False, "department_ids": [], "role_ids": [], "user_ids": []}


def normalize_perms(source: dict | None) -> dict:
    """把任意历史格式的权限记录归一化为四维形状。

    兼容三种输入：
    1. 已是四维形状（含 global/department_ids 等键）——原样归一
    2. 完整权限文档（perms 字段嵌套四维）——取嵌套
    3. 旧格式：仅 allowed_roles（按商品主体名挂载的角色单维）——等价映射为角色维
    其余/为空 —— 归一为默认拒绝。
    """
    if not source or not isinstance(source, dict):
        return _empty_perms()

    if isinstance(source.get("perms"), dict):
        source = source["perms"]

    if any(k in source for k in _NEW_SHAPE_KEYS):
        return {
            "global": bool(source.get("global", False)),
            "department_ids": list(source.get("department_ids") or []),
            "role_ids": list(source.get("role_ids") or []),
            "user_ids": list(source.get("user_ids") or []),
        }

    if "allowed_roles" in source:
        return {
            "global": False,
            "department_ids": [],
            "role_ids": list(source.get("allowed_roles") or []),
            "user_ids": [],
        }

    return _empty_perms()


def has_access(user_ctx: dict | None, perms: dict | None) -> bool:
    """四维 OR 判定：全局 ∨ 个人 ∨ 部门 ∨ 角色，任一命中即放行；否则默认拒绝。

    容忍调用方直接传入旧格式/嵌套格式（内部先归一化）。
    """
    p = normalize_perms(perms)
    if not user_ctx:
        return False
    if p["global"]:
        return True
    uid = user_ctx.get("user_id")
    if uid and uid in p["user_ids"]:
        return True
    dept = user_ctx.get("department_id")
    if dept and dept in p["department_ids"]:
        return True
    role_ids = user_ctx.get("role_ids") or []
    if role_ids and set(role_ids) & set(p["role_ids"]):
        return True
    return False
