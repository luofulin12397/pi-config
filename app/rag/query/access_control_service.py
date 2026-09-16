from app.shared.runtime.logger import step_log,logger
from app.process.query.agent.state import QueryGraphState


def access_validate(roles, item_names_roles_dict):
    """M1-05 起主体名仅用于限定检索范围；数据权限统一由召回后 node_perm_filter 四维判定。

    旧的角色交集预过滤已移除：导入时的 allowed_roles 不再决定可见性（默认拒绝 + 管理员
    通过四维权限配置接口显式授权，见 docs/api-contract.md §3）。
    """
    item_names = [name for item in item_names_roles_dict for name in item.keys()]
    return item_names, []





@step_log("search_by_embedding")
def access_control(state: QueryGraphState):
    if state.get('answer'):
        return state

    item_names_roles_dict = state.get('item_names_roles_dict')

    if not item_names_roles_dict:
        logger.warning('没有关联主体，短路结束')
        state['item_names'] = []
        state['answer'] = '没有识别到可查询的主体，请确认后再提问。'
        return state

    item_names, denied_item_names = access_validate(None, item_names_roles_dict)
    state['item_names'] = item_names
    state['denied_item_names'] = denied_item_names

    # 全部主体无权限：在节点内写入 answer（条件边路由函数改 state 不会生效）
    if not item_names and denied_item_names:
        state['answer'] = (
            f"您无权访问以下主体商品的数据：{','.join(denied_item_names)}"
        )
    elif not item_names:
        state['answer'] = '未能匹配到有权限查询的主体，请确认后再提问。'

    return state