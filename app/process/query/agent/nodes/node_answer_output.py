import sys

from app.shared.runtime.logger import node_log
from app.rag.query.answer_service import generate_answer
from app.shared.utils.pipeline_events import emit_refs, emit_skipped, emit_step
from app.shared.utils.task_utils import add_done_task, add_running_task

@node_log("node_answer_output")
def node_answer_output(state):
    """
    节点功能：生成最终回答并交付给用户（支持流式/非流式）。
    """
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    if state.get("answer"):
        # 前置短路（无主体/受限提示/未命中）已产出答案，无需组装与生成
        emit_step(state["session_id"], "compose", "done", "使用前置短路答案", state["is_stream"])
        emit_skipped(state["session_id"], ["generate"], state["is_stream"])
    else:
        emit_step(state["session_id"], "compose", "done", "提示词组装完成（仅含有权切片）", state["is_stream"])
        emit_step(state["session_id"], "generate", "running", "大模型流式生成中", state["is_stream"])
    state = generate_answer(state)
    # 引用溯源 + 拦截数（契约 refs 事件）
    emit_refs(state["session_id"], state.get("citations") or [], len(state.get("denied_knowledge_ids") or []),
              state.get("is_stream"))
    emit_step(state["session_id"], "generate", "done", "生成完成", state.get("is_stream"))
    add_done_task(state['session_id'], sys._getframe().f_code.co_name, state.get("is_stream"))
    return state
