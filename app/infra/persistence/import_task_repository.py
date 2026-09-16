"""Import 任务 Mongo 持久化。"""
from datetime import datetime

from app.shared.clients.mongo_history_utils import (
    delete_import_task,
    get_import_task,
    list_import_tasks,
    save_import_task,
)


class ImportTaskRepository:
    def upsert(
        self,
        *,
        task_id: str,
        status: str,
        filename: str = "",
        imported_by: str = "",
        allowed_roles: list[str] | None = None,
        local_dir: str = "",
        error: str = "",
    ) -> bool:
        now = datetime.now().timestamp()
        existing = get_import_task(task_id) or {}
        return save_import_task({
            "task_id": task_id,
            "status": status,
            "filename": filename,
            "imported_by": imported_by,
            "allowed_roles": allowed_roles or [],
            "local_dir": local_dir,
            "error": error,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        })

    def get(self, task_id: str) -> dict | None:
        return get_import_task(task_id)

    def list_tasks(self, limit: int = 50, imported_by: str | None = None) -> list[dict]:
        return list_import_tasks(limit=limit, imported_by=imported_by)

    def delete(self, task_id: str) -> int:
        return delete_import_task(task_id)


import_task_repository = ImportTaskRepository()
