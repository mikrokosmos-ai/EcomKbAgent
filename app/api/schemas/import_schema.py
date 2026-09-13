"""
导入 / 任务接口的响应体定义

集中声明 /upload 与 /status/{task_id} 的返回结构，供路由的 response_model 使用，
让 OpenAPI 文档展示真实的响应模型。

"""
from typing import List

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """多文件上传接口响应体（POST /upload）"""
    code: int = Field(..., description="业务状态码，成功固定为 200")
    message: str = Field(..., description="结果描述，含本次上传文件总数")
    task_ids: List[str] = Field(..., description="每个上传文件对应的任务ID列表（长度=文件数）")


class TaskStatusResponse(BaseModel):
    """任务状态查询响应体（GET /status/{task_id}）"""
    code: int = Field(..., description="业务状态码，成功固定为 200")
    task_id: str = Field(..., description="被查询的任务ID")
    status: str = Field(..., description="任务全局状态：pending/processing/completed/failed")
    done_list: List[str] = Field(..., description="已完成的节点/阶段列表")
    running_list: List[str] = Field(..., description="正在运行的节点/阶段列表")
