# -*- coding: utf-8 -*-
"""
管理端路由（:55001）。M1-02 知识单元台账。
RBAC：全部挂 require_admin（M1-04 完成菜单/按钮级展开后再细化到按钮权限）。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.schema.auth_schema import ApiResponse
from app.infra.persistence.knowledge_repository import knowledge_repository
from app.infra.persistence.permission_repository import permission_repository
from app.infra.security.perm_engine import has_access, normalize_perms
from app.infra.persistence.auth_repository import auth_repository
from app.infra.persistence.knowledge_repository import knowledge_repository
from app.infra.persistence.qa_cache_repository import qa_cache_repository
from app.infra.persistence.faq_repository import faq_repository
from app.infra.persistence.qa_log_repository import qa_log_repository
from app.shared.clients.mongo_auth_utils import get_auth_mongo_tool
from app.infra.security.deps import CurrentUser, get_current_user, require_admin, require_button
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


# ==================== 切片预览与权限弹窗数据源（M2-02） ====================

@admin_router.get("/knowledge/{knowledge_id}/chunks")
def list_chunks(
    knowledge_id: str,
    _: CurrentUser = Depends(require_button("perm")),
):
    """切片预览：按知识单元的 file_title 查询 Milvus kb_chunks。"""
    from app.infra.config.providers import infra_config
    from app.shared.clients.milvus_utils import get_milvus_client

    unit = knowledge_repository.get(knowledge_id)
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="知识单元不存在")
    file_title = unit.get("file_title", "")
    rows = get_milvus_client().query(
        collection_name=infra_config.milvus.chunks_collection,
        filter=f'file_title == "{file_title}"',
        output_fields=["chunk_id", "title", "content", "part", "start_line", "end_line"],
    )
    chunks = [{
        "id": str(r.get("chunk_id", "")),
        "title": r.get("title", ""),
        "text": r.get("content", ""),
        "part": r.get("part"),
        "lines": f"L{r.get('start_line')}-L{r.get('end_line')}" if r.get("start_line") is not None else "",
    } for r in rows]
    return ApiResponse(data=chunks)


@admin_router.get("/departments")
def list_departments(_: CurrentUser = Depends(require_button("perm"))):
    """部门列表（聚合自用户档案的 department_id；组织树模型在后续迭代落地）。"""
    users = _users_overview()
    depts = sorted({u.get("department_id") for u in users if u.get("department_id")})
    return ApiResponse(data=[{"id": d, "name": d} for d in depts])


@admin_router.get("/users")
def list_console_users(_: CurrentUser = Depends(require_button("perm"))):
    """用户轻量列表（权限弹窗的个人维选择数据源）。"""
    users = _users_overview()
    return ApiResponse(data=[{
        "id": u["id"], "name": u["name"], "username": u["username"], "departmentId": u["department_id"],
    } for u in users])


def _users_overview() -> list[dict]:
    """内部工具：聚合用户档案（id/name/username/department_id）。"""
    return [{
        "id": str(u["_id"]),
        "name": u.get("display_name") or u.get("username", ""),
        "username": u.get("username", ""),
        "department_id": u.get("department_id", ""),
    } for u in get_auth_mongo_tool().users.find(
        {}, {"_id": 1, "username": 1, "display_name": 1, "department_id": 1}
    )]


# ==================== 导入代理（前端单端口：:55001 → :55000，M2-02） ====================
_IMPORT_BASE = "http://127.0.0.1:55000"


@admin_router.post("/import/upload")
def proxy_import_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    allowed_roles: str = Form(default='["common_user"]'),
    _: CurrentUser = Depends(require_button("import")),
):
    """代理导入服务的上传接口（透传 multipart 与鉴权头）。"""
    import httpx

    auth = request.headers.get("authorization", "")
    fs = [("files", (f.filename, f.file, f.content_type or "application/octet-stream")) for f in files]
    r = httpx.post(f"{_IMPORT_BASE}/upload", files=fs, data={"allowed_roles": allowed_roles},
                   headers={"Authorization": auth}, timeout=300)
    return JSONResponse(status_code=r.status_code, content=r.json())


@admin_router.get("/import/status/{task_id}")
def proxy_import_status(task_id: str, request: Request, _: CurrentUser = Depends(require_button("import"))):
    """代理导入任务状态查询（done_list/running_list 驱动前端进度展示）。"""
    import httpx

    auth = request.headers.get("authorization", "")
    r = httpx.get(f"{_IMPORT_BASE}/status/{task_id}", headers={"Authorization": auth}, timeout=30)
    return JSONResponse(status_code=r.status_code, content=r.json())


# ==================== 审计查询与 FAQ 沉淀运营（M3-01/02） ====================

ops_router = APIRouter(prefix="/ops", tags=["ops"])

@ops_router.get("/audit/logs")
def list_audit_logs(
    limit: int = 50,
    _: CurrentUser = Depends(require_button("perm")),
):
    """问答审计日志倒序（需求 2.9.8 输出格式；挖掘/缺口/看板共用同一数据源）。"""
    logs = qa_log_repository.list_desc(limit=limit)
    for log in logs:
        if isinstance(log.get("ts"), datetime):
            log["ts"] = log["ts"].isoformat()
        log["question"] = log.get("question", "")
        log["allowedLabels"] = [k for k in log.get("allowed_ids", [])]
        log["deniedLabels"] = [k for k in log.get("denied_ids", [])]
    return ApiResponse(data=logs)


# ==================== FAQ 沉淀运营（M3-02） ====================

@ops_router.get("/faq/candidates")
def list_faq_candidates(_: CurrentUser = Depends(get_current_user)):
    return ApiResponse(data=faq_repository.list_candidates())


@ops_router.post("/faq/candidates")
def add_faq_candidate(
    body: dict,
    _: CurrentUser = Depends(require_button("faq-publish")),
):
    """手动添加候选 FAQ（自动挖掘见 M3-03）。"""
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="question 不能为空")
    cid = faq_repository.add_candidate(question=question, answer=body.get("answer", ""))
    return ApiResponse(data=faq_repository.get_candidate(cid))


@ops_router.post("/faq/candidates/{candidate_id}/publish")
def publish_faq_candidate(
    candidate_id: str,
    body: dict,
    _: CurrentUser = Depends(require_button("faq-publish")),
):
    """审核发布：候选 → 已发布并写入高速缓存。"""
    question = (body.get("question") or "").strip()
    answer = (body.get("answer") or "").strip()
    if not question or not answer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="question/answer 不能为空")
    fid = faq_repository.publish(candidate_id=candidate_id, question=question, answer=answer)
    return ApiResponse(data=faq_repository.get_published(fid))


@ops_router.post("/faq/candidates/{candidate_id}/reject")
def reject_faq_candidate(candidate_id: str, _: CurrentUser = Depends(require_button("faq-publish"))):
    n = faq_repository.reject_candidate(candidate_id)
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="候选不存在")
    return ApiResponse(data={"id": candidate_id, "status": "rejected"})


@ops_router.get("/faqs")
def list_published_faqs(_: CurrentUser = Depends(get_current_user)):
    return ApiResponse(data=faq_repository.list_published())


@ops_router.put("/faqs/{faq_id}/cache")
def toggle_faq_cache(
    faq_id: str,
    body: dict,
    _: CurrentUser = Depends(require_button("cache-toggle")),
):
    n = faq_repository.toggle_cache(faq_id, bool(body.get("enabled")))
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="FAQ 不存在")
    return ApiResponse(data=faq_repository.get_published(faq_id))


@ops_router.delete("/faqs/{faq_id}")
def delete_faq(faq_id: str, _: CurrentUser = Depends(require_button("faq-publish"))):
    n = faq_repository.delete_published(faq_id)
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="FAQ 不存在")
    return ApiResponse(data={"id": faq_id})

