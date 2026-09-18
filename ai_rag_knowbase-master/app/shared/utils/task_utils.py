"""
工具模块，负责提供 task 相关的辅助能力。
支持 Redis（REDIS_URL）与进程内存双后端。
"""
import json
from typing import Dict, List

from app.shared.clients.redis_client import get_redis_client
from .sse_utils import push_to_session

_tasks_running_list: Dict[str, List[str]] = {}
_tasks_done_list: Dict[str, List[str]] = {}
_tasks_status: Dict[str, str] = {}
_tasks_result: Dict[str, Dict[str, str]] = {}

TASK_STATUS_PENDING = "pending"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"

_NODE_NAME_TO_CN: Dict[str, str] = {
    "upload_file": "开始上传文件",
    "node_entry": "检查文件",
    "node_pdf_to_md": "PDF转Markdown",
    "node_md_img": "Markdown图片处理",
    "node_item_name_recognition": "主体名称识别",
    "node_document_split": "文档切分",
    "node_bge_embedding": "向量生成",
    "node_import_kg": "导入知识图谱",
    "node_import_milvus": "导入向量库",
    "__end__": "处理完成",
    "END": "处理完成",
    "node_query_cache": "查询缓存",
    "node_history_compress": "历史上下文压缩",
    "node_save_cache": "写入查询缓存",
    "node_access_control": "权限校验",
    # --- Query 流程节点（kb/process/query/main_graph.py）---
    "node_query_cache": "语义缓存查询",
    "node_save_cache": "语义缓存写入",
    "node_history_compress": "历史上下文压缩",
    "node_item_name_confirm": "确认问题产品",
    "node_answer_output": "生成答案",
    "node_rerank": "重排序",
    "node_rrf": "倒排融合",
    "node_web_search_mcp": "网络搜索",
    "node_search_embedding": "切片搜索",
    "node_search_embedding_hyde": "切片搜索(假设性文档)",
}


def _redis():
    return get_redis_client()


def _rk(task_id: str, suffix: str) -> str:
    return f"task:{task_id}:{suffix}"


def _ensure_task(task_id: str) -> None:
    if _redis():
        return
    if task_id not in _tasks_running_list:
        _tasks_running_list[task_id] = []
    if task_id not in _tasks_done_list:
        _tasks_done_list[task_id] = []
    if task_id not in _tasks_result:
        _tasks_result[task_id] = {}


def _to_cn(node_name: str) -> str:
    return _NODE_NAME_TO_CN.get(node_name, node_name)


def _redis_get_list(task_id: str, suffix: str) -> List[str]:
    client = _redis()
    if not client:
        return []
    raw = client.get(_rk(task_id, suffix))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _redis_set_list(task_id: str, suffix: str, values: List[str]) -> None:
    client = _redis()
    if client:
        client.set(_rk(task_id, suffix), json.dumps(values, ensure_ascii=False), ex=86400)


def add_running_task(task_id: str, node_name: str, is_stream: bool = False) -> None:
    _ensure_task(task_id)
    if _redis():
        running = _redis_get_list(task_id, "running")
        if node_name not in running:
            running.append(node_name)
            _redis_set_list(task_id, "running", running)
    else:
        running = _tasks_running_list[task_id]
        if node_name not in running:
            running.append(node_name)
    if is_stream:
        task_push_queue(task_id)


def add_done_task(task_id: str, node_name: str, is_stream: bool = False) -> None:
    _ensure_task(task_id)
    if _redis():
        running = [n for n in _redis_get_list(task_id, "running") if n != node_name]
        _redis_set_list(task_id, "running", running)
        done = _redis_get_list(task_id, "done")
        if node_name not in done:
            done.append(node_name)
            _redis_set_list(task_id, "done", done)
    else:
        running = _tasks_running_list[task_id]
        _tasks_running_list[task_id] = [n for n in running if n != node_name]
        done = _tasks_done_list[task_id]
        if node_name not in done:
            done.append(node_name)
    if is_stream:
        task_push_queue(task_id)


def set_task_result(task_id: str, key: str, value: str) -> None:
    _ensure_task(task_id)
    if _redis():
        client = _redis()
        client.hset(_rk(task_id, "result"), key, value)
        client.expire(_rk(task_id, "result"), 86400)
    else:
        _tasks_result[task_id][key] = value


def get_task_result(task_id: str, key: str, default: str = "") -> str:
    _ensure_task(task_id)
    if _redis():
        return _redis().hget(_rk(task_id, "result"), key) or default
    return _tasks_result.get(task_id, {}).get(key, default)


def get_task_status(task_id: str) -> str:
    if _redis():
        return _redis().get(_rk(task_id, "status")) or ""
    return _tasks_status.get(task_id, "")


def get_done_task_list(task_id: str) -> List[str]:
    _ensure_task(task_id)
    if _redis():
        done = _redis_get_list(task_id, "done")
    else:
        done = _tasks_done_list.get(task_id, [])
    return [_to_cn(n) for n in done]


def get_running_task_list(task_id: str) -> List[str]:
    _ensure_task(task_id)
    if _redis():
        running = _redis_get_list(task_id, "running")
    else:
        running = _tasks_running_list.get(task_id, [])
    return [_to_cn(n) for n in running]


def update_task_status(task_id: str, status_name: str, push_queue: bool = False) -> None:
    if _redis():
        client = _redis()
        client.set(_rk(task_id, "status"), status_name, ex=86400)
    else:
        _tasks_status[task_id] = status_name
    if push_queue:
        task_push_queue(task_id)


def task_push_queue(task_id: str):
    push_to_session(task_id, "progress", {
        "status": get_task_status(task_id),
        "done_list": get_done_task_list(task_id),
        "running_list": get_running_task_list(task_id),
    })


def clear_task(task_id: str):
    if _redis():
        client = _redis()
        for suffix in ("running", "done", "status", "result"):
            client.delete(_rk(task_id, suffix))
    else:
        _tasks_running_list.pop(task_id, None)
        _tasks_done_list.pop(task_id, None)
        _tasks_status.pop(task_id, None)
        _tasks_result.pop(task_id, None)
