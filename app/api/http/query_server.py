from mimetypes import guess_type
from pathlib import Path
import sys
import time
import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.http.auth_routes import auth_router
from app.api.schema.query_schema import QueryRequestParam, QueryStreamResponse, QueryNotStreamResponse , HistoryCleanResponse,HistoryResponse,HistoryItemResponse, SuggestionsResponse, SuggestionItemResponse
from app.api.schema.document_schema import DocumentPreviewResponse
from app.rag.query.document_preview_service import build_preview_html, get_document_preview
from app.infra.security.deps import CurrentUser, get_current_user, get_current_user_sse
from app.shared.runtime.logger import PROJECT_ROOT, logger
from app.infra.config.providers import settings
from app.infra.security.auth_startup import validate_jwt_secret_on_startup
from app.process.query.agent.main_graph import query_graph_app
from app.process.query.agent.state import create_query_default_state,QueryGraphState
from app.shared.utils.pipeline_events import emit_refs, emit_skipped, emit_step
from app.shared.utils.sse_utils import SSEEvent, create_sse_queue, get_sse_queue, push_to_session, sse_generator
from app.shared.utils.task_utils import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PROCESSING,
    clear_task,
    get_done_task_list,
    get_task_result,
    update_task_status,
)

from app.infra.persistence.history_repository import history_repository

# 定义fastapi对象
app = FastAPI(
    title=settings.query_app_name,
    description="描述,进行rag查询的服务对象",
    version="0.2.0"
)

# 跨域处理
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins) or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")

# M2-01：控制台前端（单端口部署，无 CORS）
_CONSOLE_DIR = Path(__file__).resolve().parents[3] / "console"
if _CONSOLE_DIR.exists():
    app.mount("/console", StaticFiles(directory=str(_CONSOLE_DIR), html=True), name="console")
    @app.get("/console")
    def _console_redirect():
        return RedirectResponse("/console/")
from app.api.http.admin_routes import admin_router  # noqa: E402  (M1-02 知识单元台账)
app.include_router(admin_router)


@app.on_event("startup")
def on_startup():
    validate_jwt_secret_on_startup()


@app.get("/html/login")
def login_html():
    login_path = PROJECT_ROOT / "app" / "resources" / "html" / "login.html"
    return FileResponse(
        path=login_path,
        media_type=guess_type(login_path.name)[0],
    )


@app.get("/static/auth.js")
def auth_js():
    js_path = PROJECT_ROOT / "app" / "resources" / "html" / "auth.js"
    return FileResponse(path=js_path, media_type="application/javascript")

# 1. 返回 chat 对应的页面
# @app.get("/html")
# def chat_html():
#     chat_html_path_obj = PROJECT_ROOT / "app" / "resources" / "html" / "chat.html"
#     return FileResponse(
#         path=chat_html_path_obj,
#         media_type=guess_type(chat_html_path_obj.name)[0],
#     )


@app.get("/html/new")
def chat_html_new():
    chat_html_path_obj = PROJECT_ROOT / "app" / "resources" / "html" / "chat_new.html"
    return FileResponse(
        path=chat_html_path_obj,
        media_type=guess_type(chat_html_path_obj.name)[0],
    )


@app.get("/html/import")
def import_html():
    """导入页仅通过问答页跳转访问，与 Query 同域以便 sessionStorage 校验。"""
    import_path = PROJECT_ROOT / "app" / "resources" / "html" / "import_new.html"
    return FileResponse(
        path=import_path,
        media_type=guess_type(import_path.name)[0],
    )

# 2. /health get 健康检查接口
@app.get("/health")
def health():
    return {
        "code":200,
        "message":"可以访问!!"
    }

# 3. /stream/{session_id} get
@app.get("/stream/{session_id}")
def stream(session_id, request: Request, _: CurrentUser = Depends(get_current_user_sse)):
    return StreamingResponse(
        sse_generator(session_id,request),
        media_type="text/event-stream"
    )

def invoke_query_graph(session_id:str,query:str,is_stream:bool=False,user_id:str=None,roles:list[str]=None,department_id:str=""):
    # 执行 动态测试
    state = create_query_default_state(
        session_id=session_id,
        original_query=query,
        is_stream=is_stream,
        user_id=user_id,
        roles=roles,
        department_id=department_id,
    )
    # 创建一个队列 session_id <-- 数据

    # 清空task_utils的数据
    clear_task(session_id)

    if is_stream and get_sse_queue(session_id) is None:
        create_sse_queue(session_id)

    started_at = time.time()
    try:
        update_task_status(session_id,TASK_STATUS_PROCESSING,is_stream)
        logger.info(f"开始执行,执行参数为:{state}")
        result_state = query_graph_app.invoke(state)
        logger.info(f"执行结束,执行结果为:{result_state}")
        update_task_status(session_id,TASK_STATUS_COMPLETED,is_stream)

        # M1-06：done 事件（来源/耗时/token 估算）
        latency_ms = int((time.time() - started_at) * 1000)
        answer_text = result_state.get("answer") or ""
        if result_state.get("cache_hit"):
            source = "semantic-cache"
        elif result_state.get("denied_knowledge_ids") and not result_state.get("allowed_knowledge_ids"):
            source = "denied"
        elif result_state.get("skip_cache"):
            source = "no-result"
        else:
            source = "rag"
        push_to_session(session_id, SSEEvent.DONE, {
            "source": source,
            "latency": latency_ms,
            "tokens": int(len(answer_text) / 1.6),  # 粗略估算（真实 usage 需 LLM 返回）
        })

        if is_stream:
            push_to_session(
                session_id,
                SSEEvent.FINAL,  # 显示图片
                {
                    "answer": result_state['answer'],
                    "status": "completed",
                    "image_urls": result_state.get("image_urls",[]),
                    "citations": result_state.get("citations", []),
                    "cache_hit": result_state.get("cache_hit", False),
                }
            )
        # 返回结果! 非流式需要
        return result_state
    except Exception as e:
        update_task_status(session_id,TASK_STATUS_FAILED,is_stream)
        push_to_session(session_id,SSEEvent.ERROR,{"error":str(e)})
        logger.exception(f"{session_id}执行出现了异常!!")


# 4. 查询和提问接口
# /query post {} | {}
@app.post("/query")
def query(
    backgroundtasks: BackgroundTasks,
    request: QueryRequestParam,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
      1. 获取stream状态
      2. true 异步 后台执行 图的调用过程 backgroundtask
         异步的返回结果
      3. false 同步 直接调用
         同步的返回结果
    :param request:
    :return:
    """
    session_id = request.session_id or str(uuid.uuid4())
    is_stream = request.is_stream
    query = request.query

    # 是否异步
    if is_stream:
        # 先创建 SSE 队列再受理任务（M1-06：客户端可在任务执行前完成订阅）
        create_sse_queue(session_id)
        # 异步执行
        backgroundtasks.add_task(invoke_query_graph,
                                 session_id=session_id,
                                 query=query,
                                 is_stream=is_stream,
                                 user_id = current_user.id,
                                 roles = current_user.roles,
                                 department_id = current_user.department_id,
                                 )
        # 立即向下
        return QueryStreamResponse(
            message=f"开启:{session_id}异步任务执行!",
            session_id=session_id
        )
    else:
        # 同步执行 死等
        final_state:QueryGraphState = invoke_query_graph(
            session_id=session_id,
            query=query,
            is_stream=is_stream,
            user_id=current_user.id,
            roles=current_user.roles,
            department_id=current_user.department_id,
        )
        return QueryNotStreamResponse(
            message=f"{session_id}对应的任务已经处理完毕!!",
            session_id=session_id,
            answer=final_state.get("answer") if final_state else None,
            done_list=get_done_task_list(session_id),
            image_urls=final_state.get("image_urls",[]) if final_state else [],
            citations=final_state.get("citations", []) if final_state else [],
            cache_hit=bool(final_state.get("cache_hit")) if final_state else False,
            allowed_ids=final_state.get("allowed_knowledge_ids", []) if final_state else [],
            denied_ids=final_state.get("denied_knowledge_ids", []) if final_state else [],
        )


@app.get("/suggestions")
def get_suggestions(limit: int = 10, current_user: CurrentUser = Depends(get_current_user)):
    """返回当前用户历史提问中频次最高的推荐问题。"""
    limit = max(1, min(limit, 20))
    rows = history_repository.top_frequent_questions(user_id=current_user.id, limit=limit)
    return SuggestionsResponse(
        user_id=current_user.id,
        items=[
            SuggestionItemResponse(question=row["question"], count=int(row.get("count", 0)))
            for row in rows
            if row.get("question")
        ],
    )


@app.get("/documents/preview", response_model=DocumentPreviewResponse)
def document_preview_json(
    file_title: str,
    start_line: int | None = Query(None, ge=1),
    end_line: int | None = Query(None, ge=1),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = get_document_preview(
        file_title=file_title,
        user_roles=current_user.roles,
        start_line=start_line,
        end_line=end_line,
    )
    return DocumentPreviewResponse(**data)


@app.get("/documents/preview/html", response_class=HTMLResponse)
def document_preview_html(
    file_title: str,
    start_line: int | None = Query(None, ge=1),
    end_line: int | None = Query(None, ge=1),
    current_user: CurrentUser = Depends(get_current_user_sse),
):
    data = get_document_preview(
        file_title=file_title,
        user_roles=current_user.roles,
        start_line=start_line,
        end_line=end_line,
    )
    return HTMLResponse(content=build_preview_html(data))


# 清空当前用户的历史对话记录
@app.delete("/history")
def remove_history(current_user: CurrentUser = Depends(get_current_user)):
    delete_count = history_repository.clear_user(user_id=current_user.id)
    logger.info(f"清空用户 {current_user.id} 的历史记录! 清空数量:{delete_count}")
    return HistoryCleanResponse(
        message=f"已清空当前用户的历史记录，共 {delete_count} 条",
        deleted_count=delete_count,
    )


@app.get("/history")
def get_history(limit: int = 50, current_user: CurrentUser = Depends(get_current_user)):
    message_list = history_repository.list_recent_by_user(user_id=current_user.id, limit=limit)
    logger.info(f"完成用户 {current_user.id} 的历史记录查询! 数量:{len(message_list)}")
    return HistoryResponse(
        user_id=current_user.id,
        items=[
            HistoryItemResponse(
                id=str(message.get("_id")),
                session_id=message.get("session_id"),
                role=message.get("role"),
                text=message.get("text"),
                rewritten_query=message.get("rewritten_query"),
                item_names=message.get("item_names"),
                image_urls=message.get("image_urls"),
                citations=message.get("citations") or [],
                ts=message.get("ts"),
            )
            for message in message_list
        ],
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.app_host, port=settings.query_app_port)









