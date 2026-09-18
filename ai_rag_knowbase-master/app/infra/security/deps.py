"""FastAPI 鉴权依赖。"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infra.persistence.auth_repository import auth_repository
from app.infra.security.jwt_utils import TokenError, decode_access_token, decode_sse_token
from app.infra.security.role_utils import ADMIN_ROLE, has_button

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: str
    username: str
    display_name: str
    roles: list[str]
    department_id: str = ""


def _build_current_user(payload: dict) -> CurrentUser:
    user_id = payload.get("sub", "")
    user = auth_repository.find_user_by_id(user_id)
    if not user or user.get("status") == "disabled":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")
    # 权限以 DB 实时角色为准，避免 JWT 内嵌 roles 过期
    roles = auth_repository.list_user_role_codes(user_id)
    return CurrentUser(
        id=user_id,
        username=user.get("username", ""),
        display_name=user.get("display_name") or user.get("username", ""),
        roles=roles,
        department_id=user.get("department_id", "") or "",

    )


def _user_from_access_token(token: str) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _build_current_user(payload)


def _user_from_sse_token(token: str) -> CurrentUser:
    try:
        payload = decode_sse_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _build_current_user(payload)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或 Token 缺失")
    return _user_from_access_token(credentials.credentials)


async def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if ADMIN_ROLE not in current_user.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


async def get_current_user_sse(
    token: str | None = Query(None, alias="token"),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """SSE EventSource 无法带 Header；优先 Bearer，其次短效 ?token=。"""
    if credentials and credentials.credentials:
        return _user_from_access_token(credentials.credentials)
    if token:
        try:
            return _user_from_sse_token(token)
        except HTTPException:
            # 兼容旧版：URL 中仍传 access token
            return _user_from_access_token(token)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或 Token 缺失")


def require_button(button_key: str):
    """按钮级功能权限依赖工厂：require_button("perm") 生成 FastAPI 依赖。
    校验当前用户角色并集是否包含指定按钮权限（admin 直通）。"""
    def _checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_button(current_user.roles, button_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少操作权限: {button_key}",
            )
        return current_user
    return _checker
