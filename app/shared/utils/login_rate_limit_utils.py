# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 登录接口简易限流

 @dependency 无

 @output check_login_rate_limit / record_login_failure / clear_login_attempts
"""

import os
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request, status

_LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "10"))
_LOGIN_WINDOW_SECONDS: int = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW", "300"))

_attempts: dict[str, Deque[float]] = defaultdict(deque)


def _client_key(request: Request, username: str) -> str:
    """
    生成限流键
    :param request: HTTP 请求
    :param username: 用户名
    :return: 限流键
    """
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"{client_ip}:{username.lower()}"


def check_login_rate_limit(request: Request, username: str) -> None:
    """
    检查登录是否触发限流
    :param request: HTTP 请求
    :param username: 用户名
    :return: None，超限则抛 HTTPException
    """
    key = _client_key(request, username)
    now = time.time()
    queue = _attempts[key]
    while queue and now - queue[0] >= _LOGIN_WINDOW_SECONDS:
        queue.popleft()
    if len(queue) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过于频繁，请 {_LOGIN_WINDOW_SECONDS // 60} 分钟后再试",
        )


def record_login_failure(request: Request, username: str) -> None:
    """
    记录一次登录失败
    :param request: HTTP 请求
    :param username: 用户名
    :return: None
    """
    _attempts[_client_key(request, username)].append(time.time())


def clear_login_attempts(request: Request, username: str) -> None:
    """
    登录成功后清除失败记录
    :param request: HTTP 请求
    :param username: 用户名
    :return: None
    """
    _attempts.pop(_client_key(request, username), None)
