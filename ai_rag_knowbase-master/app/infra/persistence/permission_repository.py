"""文档/知识单元权限元数据（MongoDB document_permissions 集合）。

权限模型演进（M1-01，expand 阶段）：
- 旧格式：allowed_roles 角色单维，按 task_id/item_name 挂载 —— 保留读写，兼容存量数据
- 新格式：perms 四维（global/department_ids/role_ids/user_ids），按 knowledge_id 挂载
- 判定统一走 app.infra.security.perm_engine（单一权威实现），本层只管存取与归一化
"""
from datetime import datetime, timezone

from app.infra.security import perm_engine
from app.shared.clients.mongo_auth_utils import get_auth_mongo_tool


class PermissionRepository:
    def upsert_document_permission(
        self,
        *,
        file_title: str,
        item_name: str,
        allowed_roles: list[str],
        imported_by: str,
        task_id: str,
        source_md_path: str = "",
        source_pdf_path: str = "",
    ) -> str:
        now = datetime.now(timezone.utc)
        tool = get_auth_mongo_tool()
        result = tool.document_permissions.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "file_title": file_title,
                    "item_name": item_name,
                    "allowed_roles": allowed_roles,
                    "imported_by": imported_by,
                    "task_id": task_id,
                    "source_md_path": source_md_path,
                    "source_pdf_path": source_pdf_path,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        if result.upserted_id:
            return str(result.upserted_id)
        doc = tool.document_permissions.find_one({"task_id": task_id}, {"_id": 1})
        return str(doc["_id"]) if doc else ""

    def list_by_item_names(self, item_names: list[str]) -> list[dict]:
        if not item_names:
            return []
        return list(
            get_auth_mongo_tool().document_permissions.find(
                {"item_name": {"$in": item_names}}
            )
        )

    def find_latest_by_file_title(self, file_title: str) -> dict | None:
        return get_auth_mongo_tool().document_permissions.find_one(
            {"file_title": file_title},
            sort=[("updated_at", -1)],
        )

    def list_all(self, limit: int = 100) -> list[dict]:
        cursor = (
            get_auth_mongo_tool()
            .document_permissions.find({})
            .sort("updated_at", -1)
            .limit(limit)
        )
        return list(cursor)

    # ---------------- 新格式：按知识单元的四维权限（expand，旧方法保留至 contract） ----------------

    def upsert_knowledge_permission(
        self,
        *,
        knowledge_id: str,
        perms: dict,
        updated_by: str = "",
    ) -> str:
        """按知识单元 upsert 四维权限；perms 先经归一化，保证落库形状一致（默认拒绝兜底）。"""
        normalized = perm_engine.normalize_perms(perms)
        now = datetime.now(timezone.utc)
        tool = get_auth_mongo_tool()
        tool.document_permissions.update_one(
            {"knowledge_id": knowledge_id},
            {
                "$set": {
                    "knowledge_id": knowledge_id,
                    "perms": normalized,
                    "updated_by": updated_by,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        doc = tool.document_permissions.find_one({"knowledge_id": knowledge_id}, {"_id": 1})
        return str(doc["_id"]) if doc else ""

    def find_by_knowledge_id(self, knowledge_id: str) -> dict | None:
        doc = get_auth_mongo_tool().document_permissions.find_one(
            {"knowledge_id": knowledge_id}
        )
        if doc:
            # 读出即归一化：旧记录（allowed_roles）对新调用方透明
            doc["perms"] = perm_engine.normalize_perms(doc)
        return doc

    def list_by_knowledge_ids(self, knowledge_ids: list[str]) -> list[dict]:
        if not knowledge_ids:
            return []
        docs = list(
            get_auth_mongo_tool().document_permissions.find(
                {"knowledge_id": {"$in": knowledge_ids}}
            )
        )
        for doc in docs:
            doc["perms"] = perm_engine.normalize_perms(doc)
        return docs


permission_repository = PermissionRepository()
