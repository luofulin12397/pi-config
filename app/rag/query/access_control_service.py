from app.shared.runtime.logger import step_log,logger
from app.process.query.agent.state import QueryGraphState


def access_validate(roles, item_names_roles_dict):
    item_names=[]
    denied_item_names=[]
    for item in item_names_roles_dict:
        for item_name, item_roles in item.items():
            intersect  = list(set(roles) & set(item_roles))
            if intersect and len(intersect) > 0:
                item_names.append(item_name)
            else:
                # 没有交集
                denied_item_names.append(item_name)
    return item_names,denied_item_names





@step_log("search_by_embedding")
def access_control(state: QueryGraphState):
    if state.get('answer'):
        return state

    roles = state.get('roles')
    item_names_roles_dict = state.get('item_names_roles_dict')

    if not roles:
        logger.error('roles为空，无法继续')
        state['item_names'] = []
        state['answer'] = '用户角色信息缺失，无法继续查询。'
        return state

    if not item_names_roles_dict:
        logger.warning('没有关联主体，短路结束')
        state['item_names'] = []
        state['answer'] = '没有识别到可查询的主体，请确认后再提问。'
        return state

    item_names, denied_item_names = access_validate(roles, item_names_roles_dict)
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