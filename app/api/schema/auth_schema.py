"""鉴权相关 Pydantic 模型。"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "ok"
    data: T | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    remember_me: bool = False


class UserInfo(BaseModel):
    id: str
    username: str
    display_name: str
    roles: list[str]
    last_login_at: Any | None = None


class LoginData(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str = ""


class RefreshData(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class LogoutRequest(BaseModel):
    refresh_token: str = ""


class RoleItem(BaseModel):
    code: str
    name: str
    description: str = ""


class DocumentPermissionItem(BaseModel):
    id: str
    file_title: str
    item_name: str
    allowed_roles: list[str]
    imported_by: str
    task_id: str
    created_at: Any | None = None
    updated_at: Any | None = None


class SseTokenData(BaseModel):
    sse_token: str
    expires_in: int
