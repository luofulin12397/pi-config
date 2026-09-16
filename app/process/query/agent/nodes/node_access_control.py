import time
import sys
from app.shared.runtime.logger import node_log
from app.rag.query.access_control_service import access_control
from app.shared.utils.task_utils import add_done_task, add_running_task

@node_log("node_access_control")
def node_access_control(state):
    """
    节点功能：确认用户问题中的核心商品名称。
    输入：state['original_query']
    输出：更新 state['item_names']
    """
    # 先登记节点开始，前端进度区可以立即感知"主体确认"已启动。
    # sys._getframe().f_code.co_name == node_item_name_confirm
    add_running_task(state["session_id"], "node_access_control", state["is_stream"])
    # 调用 rag/query service 层
    state = access_control(state)
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    return state