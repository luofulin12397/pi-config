"""用户鉴权 HTTP 路由。"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.schema.auth_schema import (
    ApiResponse,
    DocumentPermissionItem,
    LoginData,
    LoginRequest,
    LogoutRequest,
    RefreshData,
    RefreshRequest,
    RoleItem,
    SseTokenData,
    UserInfo,
)
from app.infra.persistence.auth_repository import auth_repository
from app.infra.persistence.permission_repository import permission_repository
from app.infra.security.deps import CurrentUser, get_current_user, require_admin
from app.infra.security.jwt_utils import create_access_token, create_sse_token
from app.infra.security.password_utils import verify_password
from app.shared.config.auth_config import auth_config
from app.shared.runtime.logger import logger
from app.shared.utils.login_rate_limit_utils import (
    check_login_rate_limit,
    clear_login_attempts,
    record_login_failure,
)

auth_router = APIRouter(tags=["auth"])


@auth_router.post("/login", response_model=ApiResponse[LoginData])
def login(body: LoginRequest, request: Request):
    check_login_rate_limit(request, body.username)
    user = auth_repository.find_user_by_username(body.username)
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        record_login_failure(request, body.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user.get("status") == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    user_id = str(user["_id"])
    roles = auth_repository.list_user_role_codes(user_id)
    access_token, expires_in = create_access_token(
        user_id=user_id,
        username=user["username"],
        roles=roles,
    )
    refresh_token = auth_repository.generate_refresh_token()
    refresh_days = (
        auth_config.refresh_token_remember_days
        if body.remember_me
        else auth_config.refresh_token_expire_days
    )
    auth_repository.save_refresh_token(
        user_id=user_id,
        refresh_token=refresh_token,
        expires_days=refresh_days,
    )
    auth_repository.update_last_login(user_id)
    clear_login_attempts(request, body.username)
    logger.info(f"用户 {body.username} 登录成功")

    return ApiResponse(
        code=200,
        message="登录成功",
        data=LoginData(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
            user=UserInfo(**auth_repository.user_to_dict(user, roles)),
        ),
    )


@auth_router.post("/refresh", response_model=ApiResponse[RefreshData])
def refresh_token(body: RefreshRequest):
    if not body.refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh Token 缺失")
    row = auth_repository.find_valid_refresh_token(body.refresh_token)
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh Token 无效或已过期")

    user_id = str(row["user_id"])
    user = auth_repository.find_user_by_id(user_id)
    if not user or user.get("status") == "disabled":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    roles = auth_repository.list_user_role_codes(user_id)
    access_token, expires_in = create_access_token(
        user_id=user_id,
        username=user["username"],
        roles=roles,
    )
    return ApiResponse(
        code=200,
        message="刷新成功",
        data=RefreshData(access_token=access_token, expires_in=expires_in),
    )


@auth_router.post("/logout", response_model=ApiResponse[None])
def logout(
    body: LogoutRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    if body.refresh_token:
        auth_repository.revoke_refresh_token(body.refresh_token)
    logger.info(f"用户 {current_user.username} 已注销")
    return ApiResponse(code=200, message="已注销", data=None)


@auth_router.get("/me", response_model=ApiResponse[UserInfo])
def me(current_user: CurrentUser = Depends(get_current_user)):
    user = auth_repository.find_user_by_id(current_user.id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return ApiResponse(
        code=200,
        message="ok",
        data=UserInfo(**auth_repository.user_to_dict(user)),
    )


@auth_router.get("/roles", response_model=ApiResponse[list[RoleItem]])
def list_roles(_: CurrentUser = Depends(get_current_user)):
    rows = auth_repository.list_roles()
    return ApiResponse(
        code=200,
        message="ok",
        data=[
            RoleItem(
                code=row["code"],
                name=row.get("name", row["code"]),
                description=row.get("description", ""),
            )
            for row in rows
        ],
    )


@auth_router.post("/sse-token", response_model=ApiResponse[SseTokenData])
def issue_sse_token(current_user: CurrentUser = Depends(get_current_user)):
    """签发短效 SSE Token，供 EventSource URL 使用。"""
    sse_token, expires_in = create_sse_token(
        user_id=current_user.id,
        username=current_user.username,
    )
    return ApiResponse(
        code=200,
        message="ok",
        data=SseTokenData(sse_token=sse_token, expires_in=expires_in),
    )


@auth_router.get("/permissions", response_model=ApiResponse[list[DocumentPermissionItem]])
def list_document_permissions(
    limit: int = 100,
    _: CurrentUser = Depends(require_admin),
):
    rows = permission_repository.list_all(limit=limit)
    items = []
    for row in rows:
        items.append(
            DocumentPermissionItem(
                id=str(row["_id"]),
                file_title=row.get("file_title", ""),
                item_name=row.get("item_name", ""),
                allowed_roles=row.get("allowed_roles", []),
                imported_by=row.get("imported_by", ""),
                task_id=row.get("task_id", ""),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
        )
    return ApiResponse(code=200, message="ok", data=items)
