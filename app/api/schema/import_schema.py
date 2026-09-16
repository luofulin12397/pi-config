from pydantic import BaseModel


# 上传文件的响应数据类型
class UploadSchema(BaseModel):
    code:int = 200
    message:str
    task_ids:list[str]

# 查询任务状态的数据类型
class TaskStatusSchema(BaseModel):
    code:int = 200
    task_id:str  # 当前查询的task_id
    status:str  #  # 当前task_id 对应的整体和宏观状态 processing 处理中 completed 已完成   failed 失败
    done_list:list[str]  # 当前task_id已完成的任务列表 可能有多个
    running_list:list[str] # 当前task_id正在运行的任务列表 同一时刻只有一个


class ImportTaskItem(BaseModel):
    task_id: str
    status: str
    filename: str = ""
    imported_by: str = ""
    allowed_roles: list[str] = []
    created_at: float | None = None
    updated_at: float | None = None
    error: str = ""


class ImportTaskListSchema(BaseModel):
    code: int = 200
    items: list[ImportTaskItem]


class ImportTaskDeleteSchema(BaseModel):
    code: int = 200
    message: str
    deleted_count: int