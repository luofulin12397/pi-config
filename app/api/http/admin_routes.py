# -*- coding: utf-8 -*-
"""
管理端路由（:55001）。M1-02 知识单元台账。
RBAC：全部挂 require_admin（M1-04 完成菜单/按钮级展开后再细化到按钮权限）。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.schema.auth_schema import ApiResponse
from app.infra.persistence.knowledge_repository import knowledge_repository
from app.infra.persistence.permission_repository import permission_repository
from app.infra.security.perm_engine import has_access, normalize_perms
from app.infra.persistence.qa_cache_repository import qa_cache_repository
from app.infra.security.deps import CurrentUser, require_admin, require_button
from app.rag.import_.index_service import remove_old_chunks

admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _perm_labels(perms: dict) -> list[str]:
    """权限标签摘要（台账列展示）：全局 / 部门×n / 角色×n / 个人×n / 未配置。"""
    p = normalize_perms(perms)
    labels = []
    if p["global"]:
        labels.append("全局公开")
    if p["department_ids"]:
        labels.append(f"部门×{len(p['department_ids'])}")
    if p["role_ids"]:
        labels.append(f"角色×{len(p['role_ids'])}")
    if p["user_ids"]:
        labels.append(f"个人×{len(p['user_ids'])}")
    return labels or ["未配置（默认拒绝）"]


def _to_dto(unit: dict) -> dict:
    """内部 snake_case → API camelCase（契约 docs/api-contract.md §3）。"""
    updated = unit.get("updated_at")
    kid = unit.get("knowledge_id")
    perm_doc = permission_repository.find_by_knowledge_id(kid) if kid else None
    perms = perm_doc.get("perms") if perm_doc else None
    return {
        "id": kid,
        "title": unit.get("title"),
        "format": unit.get("format"),
        "category": unit.get("category"),
        "enabled": bool(unit.get("enabled", False)),
        "chunksCount": unit.get("chunks_count", 0),
        "itemName": unit.get("item_name", ""),
        "fileTitle": unit.get("file_title", ""),
        "updatedAt": updated.isoformat() if isinstance(updated, datetime) else None,
        "perms": perms,
        "permLabels": _perm_labels(perms) if perms else ["未配置（默认拒绝）"],
    }


class KnowledgeUpdateRequest(BaseModel):
    title: str | None = None
    category: str | None = None
    enabled: bool | None = None


@admin_router.get("/knowledge", response_model=ApiResponse[list[dict]])
def list_knowledge(
    kw: str | None = None,
    category: str | None = None,
    limit: int = 100,
    _: CurrentUser = Depends(require_admin),
):
    return ApiResponse(data=[_to_dto(u) for u in knowledge_repository.list_units(kw=kw, category=category, limit=limit)])


@admin_router.put("/knowledge/{knowledge_id}", response_model=ApiResponse[dict])
def update_knowledge(
    knowledge_id: str,
    body: KnowledgeUpdateRequest,
    _: CurrentUser = Depends(require_admin),
):
    unit = knowledge_repository.get(knowledge_id)
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="知识单元不存在")
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="无可更新字段")
    knowledge_repository.update(knowledge_id, patch)
    # 停用会使已缓存答案失效：清当前版本语义缓存（ISS：缓存与知识变更一致性）
    if patch.get("enabled") is False:
        removed = qa_cache_repository.delete_by_version()
        if removed:
            print(f"[admin] 知识单元停用，已清空语义缓存 {removed} 条")
    return ApiResponse(data=_to_dto(knowledge_repository.get(knowledge_id)))


@admin_router.delete("/knowledge/{knowledge_id}", response_model=ApiResponse[dict])
def delete_knowledge(
    knowledge_id: str,
    _: CurrentUser = Depends(require_admin),
):
    unit = knowledge_repository.get(knowledge_id)
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="知识单元不存在")
    # 先删台账，再清向量与语义缓存（缓存中的旧答案必须随知识删除失效）
    knowledge_repository.delete(knowledge_id)
    removed = qa_cache_repository.delete_by_version()
    if removed:
        print(f"[admin] 知识单元删除，已清空语义缓存 {removed} 条")
    file_title = unit.get("file_title", "")
    if file_title:
        remove_old_chunks(file_title)
    return ApiResponse(data={"id": knowledge_id, "fileTitle": file_title})


# ==================== 四维数据权限配置（M1-03） ====================

class PermissionUpdateRequest(BaseModel):
    global_: bool = False
    department_ids: list[str] = []
    role_ids: list[str] = []
    user_ids: list[str] = []

    model_config = {"populate_by_name": True}


@admin_router.get("/knowledge/{knowledge_id}/permissions")
def get_permissions(
    knowledge_id: str,
    _: CurrentUser = Depends(require_button("perm")),
):
    """回显知识单元四维权限（旧记录归一化后返回）。"""
    doc = permission_repository.find_by_knowledge_id(knowledge_id)
    perms = doc.get("perms") if doc else {"global": False, "department_ids": [], "role_ids": [], "user_ids": []}
    return ApiResponse(data={"id": knowledge_id, "perms": perms, "labels": _perm_labels(perms)})


@admin_router.put("/knowledge/{knowledge_id}/permissions")
def set_permissions(
    knowledge_id: str,
    body: PermissionUpdateRequest,
    current_user: CurrentUser = Depends(require_button("perm")),
):
    """保存四维权限并即时生效：仓储读出即归一化（问答管线无独立权限缓存）；
    同时清空当前版本语义缓存——权限收回后，已缓存答案不得继续返回（防泄漏）。"""
    perms = normalize_perms({
        "global": body.global_,
        "department_ids": body.department_ids,
        "role_ids": body.role_ids,
        "user_ids": body.user_ids,
    })
    permission_repository.upsert_knowledge_permission(
        knowledge_id=knowledge_id, perms=perms, updated_by=current_user.id
    )
    removed = qa_cache_repository.delete_by_version()
    return ApiResponse(data={
        "id": knowledge_id, "perms": perms, "labels": _perm_labels(perms),
        "cacheInvalidated": removed,
    })
