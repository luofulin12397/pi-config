# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 服务启动时 JWT 配置校验

 @dependency auth_config

 @output validate_jwt_secret_on_startup
"""

import os

from app.shared.config.auth_config import auth_config
from app.shared.runtime.logger import logger

_DEFAULT_SECRET = "change-me-in-production-use-long-random-string"


def validate_jwt_secret_on_startup() -> None:
    """
    启动时检查 JWT_SECRET_KEY 是否已配置
    :return: None
    """
    secret = auth_config.jwt_secret_key
    if secret and secret != _DEFAULT_SECRET:
        return
    env = os.getenv("APP_ENV", "development").lower()
    msg = "JWT_SECRET_KEY 仍为默认值，生产环境请务必修改"
    if env in ("production", "prod"):
        raise RuntimeError(msg)
    logger.warning(msg)
