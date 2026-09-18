"""用户、角色、Token 数据访问。"""
import hashlib
import secrets
from datetime import timedelta
from typing import Any

from bson import ObjectId

from app.shared.clients.mongo_auth_utils import get_auth_mongo_tool, utc_now
from app.shared.runtime.logger import logger


class AuthRepository:
    def find_user_by_username(self, username: str) -> dict | None:
        return get_auth_mongo_tool().users.find_one({"username": username})

    def find_user_by_id(self, user_id: str) -> dict | None:
        try:
            oid = ObjectId(user_id)
        except Exception:
            return None
        return get_auth_mongo_tool().users.find_one({"_id": oid})

    def list_user_role_codes(self, user_id: str) -> list[str]:
        try:
            oid = ObjectId(user_id)
        except Exception:
            return []
        rows = get_auth_mongo_tool().user_roles.find({"user_id": oid})
        return [row["role_code"] for row in rows]

    def list_roles(self) -> list[dict]:
        return list(get_auth_mongo_tool().roles.find({}, {"_id": 0}))

    def update_last_login(self, user_id: str) -> None:
        get_auth_mongo_tool().users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_login_at": utc_now()}},
        )

    @staticmethod
    def hash_refresh_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_refresh_token() -> str:
        return secrets.token_urlsafe(32)

    def save_refresh_token(
        self,
        *,
        user_id: str,
        refresh_token: str,
        expires_days: int,
    ) -> None:
        token_hash = self.hash_refresh_token(refresh_token)
        get_auth_mongo_tool().refresh_tokens.insert_one(
            {
                "user_id": ObjectId(user_id),
                "token_hash": token_hash,
                "expires_at": utc_now() + timedelta(days=expires_days),
                "revoked": False,
                "created_at": utc_now(),
            }
        )

    def find_valid_refresh_token(self, refresh_token: str) -> dict | None:
        token_hash = self.hash_refresh_token(refresh_token)
        row = get_auth_mongo_tool().refresh_tokens.find_one(
            {
                "token_hash": token_hash,
                "revoked": False,
                "expires_at": {"$gt": utc_now()},
            }
        )
        return row

    def revoke_refresh_token(self, refresh_token: str) -> None:
        token_hash = self.hash_refresh_token(refresh_token)
        get_auth_mongo_tool().refresh_tokens.update_one(
            {"token_hash": token_hash},
            {"$set": {"revoked": True}},
        )

    def revoke_all_user_tokens(self, user_id: str) -> None:
        get_auth_mongo_tool().refresh_tokens.update_many(
            {"user_id": ObjectId(user_id), "revoked": False},
            {"$set": {"revoked": True}},
        )

    def user_to_dict(self, user: dict, roles: list[str] | None = None) -> dict[str, Any]:
        uid = str(user["_id"])
        role_codes = roles if roles is not None else self.list_user_role_codes(uid)
        return {
            "id": uid,
            "username": user.get("username", ""),
            "display_name": user.get("display_name") or user.get("username", ""),
            "roles": role_codes,
            "last_login_at": user.get("last_login_at"),
        }


auth_repository = AuthRepository()
