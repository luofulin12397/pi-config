"""MongoDB 用户鉴权与权限集合访问。"""
from datetime import datetime, timezone

from bson import ObjectId

from app.shared.clients.mongo_history_utils import get_history_mongo_tool
from app.shared.runtime.logger import logger
from pymongo import ASCENDING


class AuthMongoTool:
    """复用已有 Mongo 连接，管理 users / roles / user_roles / refresh_tokens / document_permissions。"""

    def __init__(self):
        history_tool = get_history_mongo_tool()
        self.db = history_tool.db
        self.users = self.db["auth_users"]
        self.roles = self.db["auth_roles"]
        self.user_roles = self.db["auth_user_roles"]
        self.refresh_tokens = self.db["auth_refresh_tokens"]
        self.document_permissions = self.db["document_permissions"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.users.create_index([("username", ASCENDING)], unique=True)
        self.roles.create_index([("code", ASCENDING)], unique=True)
        self.user_roles.create_index([("user_id", ASCENDING), ("role_code", ASCENDING)], unique=True)
        self.refresh_tokens.create_index([("token_hash", ASCENDING)], unique=True)
        self.refresh_tokens.create_index([("user_id", ASCENDING)])
        self.document_permissions.create_index([("item_name", ASCENDING)])
        self.document_permissions.create_index([("file_title", ASCENDING)])
        self.document_permissions.create_index([("task_id", ASCENDING)])


_auth_mongo_tool: AuthMongoTool | None = None


def get_auth_mongo_tool() -> AuthMongoTool:
    global _auth_mongo_tool
    if _auth_mongo_tool is None:
        _auth_mongo_tool = AuthMongoTool()
        logger.info("AuthMongoTool initialized")
    return _auth_mongo_tool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_object_id(value: str) -> ObjectId:
    return ObjectId(value)
