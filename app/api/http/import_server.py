"""
导入服务 HTTP 入口模块，直接承载导入接口与相关接口业务逻辑。
"""
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.http.auth_routes import auth_router
from app.api.schema.import_schema import (
    ImportTaskDeleteSchema,
    ImportTaskItem,
    ImportTaskListSchema,
    TaskStatusSchema,
    UploadSchema,
)
from app.infra.persistence.import_task_repository import import_task_repository
from app.infra.persistence.permission_repository import permission_repository
from app.infra.security.deps import CurrentUser, get_current_user
from app.infra.security.role_utils import validate_import_allowed_roles
from app.rag.import_.output_cleanup_service import cleanup_old_output
from app.process.import_.agent.main_graph import kb_import_app
from app.process.import_.agent.state import create_default_state
from app.infra.config.providers import settings
from app.infra.security.auth_startup import validate_jwt_secret_on_startup
from app.shared.runtime.logger import PROJECT_ROOT, logger
from app.shared.utils.task_utils import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PENDING,
    TASK_STATUS_PROCESSING,
    get_done_task_list,
    get_running_task_list,
    get_task_status,
    update_task_status,
    add_running_task,
    add_done_task,
)

app = FastAPI(
    title=settings.import_app_name,
    description="企业化 RAG 导入服务，负责文件上传、导入执行与状态查询。",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins) or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")


@app.on_event("startup")
def on_startup():
    validate_jwt_secret_on_startup()
    cleanup_old_output()


@app.get("/html/new")
@app.get("/html/import")
@app.get("/html/login")
def redirect_to_query_portal():
    """导入服务不提供 HTML 入口，统一跳转到 Query 问答页。"""
    host = settings.app_host if settings.app_host not in ("0.0.0.0", "") else "127.0.0.1"
    return RedirectResponse(
        url=f"http://{host}:{settings.query_app_port}/html/new",
        status_code=302,
    )


@app.get("/status/{task_id}")
def task_status(task_id: str, _: CurrentUser = Depends(get_current_user)):
    logger.info(f"获取任务状态接口被调用,task_id:{task_id}")
    return TaskStatusSchema(
        code=200,
        task_id=task_id,
        status=get_task_status(task_id),
        done_list=get_done_task_list(task_id),
        running_list=get_running_task_list(task_id),
    )


def invoke_graph(
    task_id: str,
    local_file_path: Path,
    local_dir: Path,
    allowed_roles: list[str],
    imported_by: str,

):
    state = create_default_state(
        task_id=task_id,
        local_file_path=str(local_file_path),
        local_dir=str(local_dir),
        allowed_roles=allowed_roles,
        imported_by=imported_by,
    )

    try:
        logger.info(f"{task_id}对应的文件解析任务开始执行! 参数state keys:{list(state.keys())}")
        import_task_repository.upsert(
            task_id=task_id,
            status=TASK_STATUS_PROCESSING,
            imported_by=imported_by,
            allowed_roles=allowed_roles,
            local_dir=str(local_dir),
        )
        update_task_status(task_id, TASK_STATUS_PROCESSING)
        final_state = kb_import_app.invoke(state)
        logger.info(f"{task_id}对应的文件解析任务完成! item_name={final_state.get('item_name')}")
        permission_repository.upsert_document_permission(
            file_title=final_state.get("file_title", ""),
            item_name=final_state.get("item_name", ""),
            allowed_roles=allowed_roles,
            imported_by=imported_by,
            task_id=task_id,
            source_md_path=final_state.get("md_path", ""),
            source_pdf_path=final_state.get("local_file_path", "") or final_state.get("pdf_path", ""),
        )
        update_task_status(task_id, TASK_STATUS_COMPLETED)
        import_task_repository.upsert(
            task_id=task_id,
            status=TASK_STATUS_COMPLETED,
            imported_by=imported_by,
            allowed_roles=allowed_roles,
            local_dir=str(local_dir),
        )
    except Exception as exc:
        update_task_status(task_id, TASK_STATUS_FAILED)
        import_task_repository.upsert(
            task_id=task_id,
            status=TASK_STATUS_FAILED,
            imported_by=imported_by,
            allowed_roles=allowed_roles,
            local_dir=str(local_dir),
            error=str(exc),
        )
        logger.exception(f"===== 全流程测试运行失败 =====")


@app.get("/tasks", response_model=ImportTaskListSchema)
def list_tasks(limit: int = 50, current_user: CurrentUser = Depends(get_current_user)):
    from app.infra.security.role_utils import ADMIN_ROLE

    imported_by = None if ADMIN_ROLE in current_user.roles else current_user.id
    rows = import_task_repository.list_tasks(limit=max(1, min(limit, 100)), imported_by=imported_by)
    return ImportTaskListSchema(
        items=[
            ImportTaskItem(
                task_id=row.get("task_id", ""),
                status=row.get("status", ""),
                filename=row.get("filename", ""),
                imported_by=row.get("imported_by", ""),
                allowed_roles=row.get("allowed_roles", []),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                error=row.get("error", ""),
            )
            for row in rows
        ]
    )


@app.delete("/tasks/{task_id}", response_model=ImportTaskDeleteSchema)
def delete_task(task_id: str, current_user: CurrentUser = Depends(get_current_user)):
    from app.infra.security.role_utils import ADMIN_ROLE

    row = import_task_repository.get(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    if ADMIN_ROLE not in current_user.roles and row.get("imported_by") != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除该任务")
    deleted = import_task_repository.delete(task_id)
    local_dir = row.get("local_dir")
    if local_dir:
        path = Path(local_dir)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    return ImportTaskDeleteSchema(message="任务已删除", deleted_count=deleted)


def _start_import_task(
    backgroundtasks: BackgroundTasks,
    current_file: UploadFile,
    roles_list: list[str],
    imported_by: str,
) -> str:
    task_id = str(uuid.uuid4())
    add_running_task(task_id, "upload_file")
    local_dir_path_obj = PROJECT_ROOT / "output" / datetime.now().strftime("%Y%m%d") / task_id
    local_dir_path_obj.mkdir(parents=True, exist_ok=True)

    local_file_path_obj = local_dir_path_obj / current_file.filename
    with local_file_path_obj.open("wb") as file_buffer:
        shutil.copyfileobj(current_file.file, file_buffer)

    add_done_task(task_id, "upload_file")
    import_task_repository.upsert(
        task_id=task_id,
        status=TASK_STATUS_PENDING,
        filename=current_file.filename,
        imported_by=imported_by,
        allowed_roles=roles_list,
        local_dir=str(local_dir_path_obj),
    )
    backgroundtasks.add_task(
        invoke_graph,
        task_id=task_id,
        local_file_path=local_file_path_obj,
        local_dir=local_dir_path_obj,
        allowed_roles=roles_list,
        imported_by=imported_by,
    )
    return task_id


@app.post("/upload")
def upload_and_invoke_graph(
    backgroundtasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    allowed_roles: str = Form(default='["common_user"]'),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个文件")

    try:
        roles_list = json.loads(allowed_roles)
        if not isinstance(roles_list, list) or len(roles_list) == 0:
            roles_list = ["common_user"]
        roles_list = [str(r) for r in roles_list]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="allowed_roles 不是合法 JSON 数组")

    roles_list = validate_import_allowed_roles(roles_list, current_user.roles)

    task_ids = [
        _start_import_task(backgroundtasks, f, roles_list, current_user.id)
        for f in files
    ]

    return UploadSchema(
        code=200,
        message=f"已提交 {len(task_ids)} 个导入任务",
        task_ids=task_ids,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app_host, port=settings.import_app_port)
