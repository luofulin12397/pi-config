"""SSE 工具：支持 Redis List 与进程内 Queue 双后端。"""
import asyncio
import json
import queue
from typing import Any, Dict, Optional

from fastapi import Request

from app.shared.clients.redis_client import get_redis_client


class SSEEvent:
    READY = "ready"
    PROGRESS = "progress"
    DELTA = "delta"
    STEP = "step"   # M1-06：管线步骤（契约 §0）
    REFS = "refs"    # M1-06：引用溯源 + 拦截数
    DONE = "done"    # M1-06：来源/耗时/token
    FINAL = "final"
    ERROR = "error"
    CLOSE = "__close__"


_session_stream: Dict[str, queue.Queue] = {}


def _redis():
    return get_redis_client()


def _sse_key(session_id: str) -> str:
    return f"sse:{session_id}"


def get_sse_queue(session_id: str) -> Optional[queue.Queue]:
    if _redis():
        return queue.Queue()
    return _session_stream.get(session_id)


def create_sse_queue(session_id: str) -> queue.Queue:
    if _redis():
        client = _redis()
        client.delete(_sse_key(session_id))
        return queue.Queue()
    q = queue.Queue()
    _session_stream[session_id] = q
    return q


def remove_sse_queue(session_id: str):
    if _redis():
        _redis().delete(_sse_key(session_id))
    else:
        _session_stream.pop(session_id, None)


def _sse_pack(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def push_to_session(session_id: str, event: str, data: Dict[str, Any]):
    if _redis():
        client = _redis()
        client.rpush(_sse_key(session_id), json.dumps({"event": event, "data": data}, ensure_ascii=False))
        client.expire(_sse_key(session_id), 3600)
        return
    stream_queue = _session_stream.get(session_id)
    if stream_queue:
        stream_queue.put({"event": event, "data": data})


def _blocking_redis_pop(session_id: str, timeout: float):
    client = _redis()
    if not client:
        return None
    result = client.blpop(_sse_key(session_id), timeout=int(timeout) or 1)
    if not result:
        return None
    _, raw = result
    return json.loads(raw)


async def sse_generator(session_id: str, request: Request):
    loop = asyncio.get_running_loop()
    use_redis = _redis() is not None
    stream_queue = None if use_redis else _session_stream.get(session_id)

    try:
        yield _sse_pack("ready", {})
        # M1-06：前端通常先订阅后提问——等待队列创建（最长 10s）而非立即断开
        if not use_redis:
            waited = 0.0
            while stream_queue is None and waited < 10.0:
                await asyncio.sleep(0.2)
                waited += 0.2
                stream_queue = _session_stream.get(session_id)
            if stream_queue is None:
                return
        while True:
            if await request.is_disconnected():
                break
            try:
                if use_redis:
                    msg = await loop.run_in_executor(None, _blocking_redis_pop, session_id, 1.0)
                    if msg is None:
                        continue
                else:
                    msg = await loop.run_in_executor(None, stream_queue.get, True, 1.0)
            except queue.Empty:
                continue

            event = msg.get("event")
            data = msg.get("data")
            if event == SSEEvent.CLOSE:
                break
            yield _sse_pack(event, data)
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        return
    finally:
        remove_sse_queue(session_id)
