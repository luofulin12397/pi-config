#!/usr/bin/env python3
"""种子数据初始化脚本。
在首次部署时运行，创建默认角色和 admin 用户。

用法：
    uv run python scripts/seed_auth.py
    或
    .venv\Scripts\python.exe scripts/seed_auth.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.infra.security.password_utils import hash_password
from app.infra.security.role_utils import DEFAULT_ROLE_PERMS
from app.shared.clients.mongo_auth_utils import get_auth_mongo_tool, utc_now
from app.shared.runtime.logger import logger

SEED_USERNAME = "admin"
SEED_PASSWORD = "admin123"
SEED_DISPLAY_NAME = "系统管理员"

ROLES = [
    {"code": "admin", "name": "管理员", "description": "系统管理员，拥有全部权限"},
    {"code": "common_user", "name": "普通用户", "description": "普通用户，可访问被授权的文档"},
    {"code": "engineer", "name": "工程师", "description": "工程师角色"},
    {"code": "operator", "name": "操作员", "description": "操作员角色"},
]


def seed_roles(tool) -> dict[str, str]:
    """创建角色并返回 code -> _id 映射。"""
    role_id_map = {}
    for role in ROLES:
        existing = tool.roles.find_one({"code": role["code"]})
        if existing:
            role_id_map[role["code"]] = existing["_id"]
            logger.info(f"角色已存在: {role['code']}")
        else:
            result = tool.roles.insert_one({
                "code": role["code"],
                "name": role["name"],
                "description": role["description"],
                **DEFAULT_ROLE_PERMS.get(role["code"], {"menus": ["chat"], "buttons": ["ask"]}),
                "created_at": utc_now(),
            })
            role_id_map[role["code"]] = result.inserted_id
            logger.info(f"角色已创建: {role['code']}")
        # 迁移补齐：存量角色缺 menus/buttons 时按默认配置回填
        perms = DEFAULT_ROLE_PERMS.get(role["code"])
        if perms:
            tool.roles.update_one(
                {"code": role["code"]},
                {"$set": {"menus": perms["menus"], "buttons": perms["buttons"]}},
            )
    return role_id_map


def seed_admin_user(tool) -> str | None:
    """创建 admin 用户，已存在则跳过。"""
    existing = tool.users.find_one({"username": SEED_USERNAME})
    if existing:
        user_id = str(existing["_id"])
        logger.info(f"用户已存在: {SEED_USERNAME} (id={user_id})")
        return user_id

    password_hash = hash_password(SEED_PASSWORD)
    result = tool.users.insert_one({
        "username": SEED_USERNAME,
        "password_hash": password_hash,
        "display_name": SEED_DISPLAY_NAME,
        "status": "active",
        "created_at": utc_now(),
        "last_login_at": None,
    })
    user_id = str(result.inserted_id)
    logger.info(f"用户已创建: {SEED_USERNAME} / {SEED_PASSWORD} (id={user_id})")
    return user_id


def assign_admin_role(tool, user_id: str, role_id_map: dict[str, str]):
    """将 admin 角色关联到 admin 用户。"""
    from bson import ObjectId

    existing = tool.user_roles.find_one({
        "user_id": ObjectId(user_id),
        "role_code": "admin",
    })
    if existing:
        logger.info("admin 角色已关联，跳过")
        return

    tool.user_roles.insert_one({
        "user_id": ObjectId(user_id),
        "role_code": "admin",
        "created_at": utc_now(),
    })
    logger.info("admin 角色已关联到 admin 用户")

    # 也关联 common_user 角色
    existing_cu = tool.user_roles.find_one({
        "user_id": ObjectId(user_id),
        "role_code": "common_user",
    })
    if not existing_cu:
        tool.user_roles.insert_one({
            "user_id": ObjectId(user_id),
            "role_code": "common_user",
            "created_at": utc_now(),
        })
        logger.info("common_user 角色已关联到 admin 用户")


def main():
    logger.info("===== 开始初始化种子数据 =====")
    tool = get_auth_mongo_tool()
    role_id_map = seed_roles(tool)
    user_id = seed_admin_user(tool)
    if user_id:
        assign_admin_role(tool, user_id, role_id_map)
    logger.info("===== 种子数据初始化完成 =====")


if __name__ == "__main__":
    main()
