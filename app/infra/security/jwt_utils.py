"""JWT 签发与解析。"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.shared.config.auth_config import auth_config


class TokenError(Exception):
    """Token 无效或过期。"""


def create_access_token(*, user_id: str, username: str, roles: list[str]) -> tuple[str, int]:
    expires_minutes = auth_config.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": user_id,
        "username": username,
        "roles": roles,
        "type": "access",
        "exp": expire,
    }
    token = jwt.encode(payload, auth_config.jwt_secret_key, algorithm=auth_config.jwt_algorithm)
    return token, expires_minutes * 60


def create_sse_token(*, user_id: str, username: str) -> tuple[str, int]:
    """短效 SSE 专用 Token，避免长期 access token 出现在 URL。"""
    expires_minutes = int(os.getenv("JWT_SSE_TOKEN_EXPIRE_MINUTES", "5"))
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": user_id,
        "username": username,
        "type": "sse",
        "exp": expire,
    }
    token = jwt.encode(payload, auth_config.jwt_secret_key, algorithm=auth_config.jwt_algorithm)
    return token, expires_minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            auth_config.jwt_secret_key,
            algorithms=[auth_config.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Token 无效或已过期") from exc
    if payload.get("type") != "access":
        raise TokenError("Token 类型错误")
    return payload


def decode_sse_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            auth_config.jwt_secret_key,
            algorithms=[auth_config.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise TokenError("SSE Token 无效或已过期") from exc
    if payload.get("type") != "sse":
        raise TokenError("SSE Token 类型错误")
    return payload
