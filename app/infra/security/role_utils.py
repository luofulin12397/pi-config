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
