"""
M1-06 SSE 管线事件流 集成验收（契约 docs/api-contract.md §0）。
前置：双服务运行；台账中已有知识单元（先跑 test_m1_ledger.py 或 test_m1_scenario.py）。
运行：.venv/bin/python scripts/test_m1_sse.py
"""
from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUERY = "http://127.0.0.1:55001"
STEP_KEYS = ["faq", "context", "search", "auth", "compose", "generate"]
PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def consume_sse(token: str, session_id: str, events: list, stop: threading.Event):
    """订阅 /stream/{sid}，解析 SSE 帧，直到 final/error/close 或超时。"""
    with httpx.stream("GET", f"{QUERY}/stream/{session_id}",
                      params={"token": token}, timeout=300) as resp:
        event, data_lines = None, []
        for line in resp.iter_lines():
            if stop.is_set():
                return
            if line == "":
                if event and data_lines:
                    try:
                        data = json.loads("\n".join(data_lines))
                    except json.JSONDecodeError:
                        data = {}
                    events.append({"event": event, "data": data})
                    if event in ("final", "error", "__close__"):
                        stop.set()
                        return
                event, data_lines = None, []
                continue
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())


def main():
    token = httpx.post(f"{QUERY}/auth/login", json={"username": "admin", "password": "admin123"},
                       timeout=15).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 前置：清空语义缓存（避免历史同题缓存命中干扰六步序列断言）
    from app.shared.clients.mongo_qa_cache_utils import _get_qa_cache_collection
    _get_qa_cache_collection().delete_many({})

    # 前置：确保台账有知识单元
    units = httpx.get(f"{QUERY}/admin/knowledge", headers=headers, timeout=10).json()["data"]
    if not units:
        doc = Path("/tmp/union-test/差旅报销标准.md")
        with open(doc, "rb") as f:
            r = httpx.post("http://127.0.0.1:55000/upload",
                           files=[("files", (doc.name, f, "text/markdown"))],
                           data={"allowed_roles": '["admin","common_user"]'}, headers=headers, timeout=60)
        task_id = r.json()["task_ids"][0]
        for _ in range(60):
            if httpx.get(f"http://127.0.0.1:55000/status/{task_id}", timeout=10).json().get("status") == "completed":
                break
            time.sleep(3)

    # 发起流式问答（is_stream=True），随后订阅 SSE
    session_id = str(uuid.uuid4())
    events: list = []
    stop = threading.Event()
    t = threading.Thread(target=consume_sse, args=(token, session_id, events, stop), daemon=True)
    t.start()
    time.sleep(0.5)  # 等 SSE 订阅建立

    r = httpx.post(f"{QUERY}/query", json={"query": "差旅报销的住宿标准和餐补是多少？", "is_stream": True, "session_id": session_id},
                   headers=headers, timeout=30)
    check("流式任务受理", r.status_code == 200, r.text[:120])

    t.join(timeout=180)
    steps = [e["data"] for e in events if e["event"] == "step"]
    deltas = [e["data"]["delta"] for e in events if e["event"] == "delta"]
    refs = next((e["data"] for e in events if e["event"] == "refs"), None)
    done = next((e["data"] for e in events if e["event"] == "done"), None)
    final = next((e["data"] for e in events if e["event"] == "final"), None)

    seq = [s["key"] for s in steps if s["status"] in ("running", "done")]
    check("六步 step 事件按序出现", all(k in seq for k in STEP_KEYS), f"seq={seq}")
    check("步骤顺序符合契约", seq[:6] == STEP_KEYS, f"seq={seq}")
    if "faq" in [s["key"] for s in steps]:
        faq_detail = next((s.get("detail", "") for s in reversed(steps) if s["key"] == "faq"), "")
        check("faq 步骤含命中/未命中 detail", bool(faq_detail), faq_detail)

    answer = (final or {}).get("answer", "")
    check("delta 拼接与最终答案一致", deltas and "".join(deltas) == answer,
          f"delta_len={sum(len(d) for d in deltas)} answer_len={len(answer)}")
    check("refs 事件含引用与拦截数", isinstance(refs, dict) and "refs" in refs and "deniedCount" in refs, str(refs)[:120])
    check("done 事件含来源/耗时/token", isinstance(done, dict) and done.get("source") in ("rag", "semantic-cache", "denied", "no-result")
          and isinstance(done.get("latency"), int) and "tokens" in done, str(done))
    check("最终答案非空", len(answer) > 20, answer[:60])

    # 语义缓存命中场景：同题再问一次 → context/search/auth/compose/generate 应为 skipped
    session_id2 = str(uuid.uuid4())
    events2: list = []
    stop2 = threading.Event()
    t2 = threading.Thread(target=consume_sse, args=(token, session_id2, events2, stop2), daemon=True)
    t2.start()
    time.sleep(0.5)
    httpx.post(f"{QUERY}/query", json={"query": "差旅报销的住宿标准和餐补是多少？", "is_stream": True, "session_id": session_id2},
               headers=headers, timeout=30)
    t2.join(timeout=60)
    steps2 = [e["data"] for e in events2 if e["event"] == "step"]
    skipped_keys = [s["key"] for s in steps2 if s["status"] == "skipped"]
    done_keys2 = [s["key"] for s in steps2 if s["status"] == "done"]
    check("缓存命中时后续步骤标记 skipped", all(k in skipped_keys for k in ["context", "search", "auth", "compose", "generate"]),
          f"skipped={skipped_keys} done={done_keys2}")

    print(f"\nPASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
