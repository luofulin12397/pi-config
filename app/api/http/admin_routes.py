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
from app.infra.persistence.qa_cache_repository import qa_cache_repository
from app.infra.security.deps import CurrentUser, require_admin
from app.rag.import_.index_service import remove_old_chunks

admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _to_dto(unit: dict) -> dict:
    """内部 snake_case → API camelCase（契约 docs/api-contract.md §3）。"""
    updated = unit.get("updated_at")
    return {
        "id": unit.get("knowledge_id"),
        "title": unit.get("title"),
        "format": unit.get("format"),
        "category": unit.get("category"),
        "enabled": bool(unit.get("enabled", False)),
        "chunksCount": unit.get("chunks_count", 0),
        "itemName": unit.get("item_name", ""),
        "fileTitle": unit.get("file_title", ""),
        "updatedAt": updated.isoformat() if isinstance(updated, datetime) else None,
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
