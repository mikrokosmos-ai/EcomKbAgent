"""
任务状态查询接口路由

import 与 query 流程共享同一套任务追踪存储（task_utils），因此统一收敛到此路由，
消除原先 import_router 与 query_router 中重复注册 /status/{task_id} 的问题。
返回字段与历史实现保持一致（code / task_id / status / done_list / running_list）。
"""
from typing import Any, Dict

from fastapi import APIRouter

from app.core.logger import logger
from app.utils.task_utils import (
    get_task_status, get_done_task_list, get_running_task_list
)

task_router = APIRouter(tags=["task"])


@task_router.get("/status/{task_id}", summary="任务状态查询", description="根据TaskID查询单个任务的进度和全局状态")
async def get_task_progress(task_id: str):
    """
    任务状态查询接口
    前端轮询此接口（如每秒1次），获取任务的实时处理进度
    返回数据均来自内存中的任务管理字典（task_utils.py），高性能无IO

    :param task_id: 全局唯一任务ID（查询流程即 session_id，导入流程即上传返回的 task_id）
    :return: 包含任务全局状态、已完成节点、运行中节点的JSON响应
    """
    # 构造任务状态返回体（import 与 query 流程共享同一 task_utils 任务存储）
    task_status_info: Dict[str, Any] = {
        "code": 200,
        "task_id": task_id,
        "status": get_task_status(task_id),  # 任务全局状态：pending/processing/completed/failed
        "done_list": get_done_task_list(task_id),  # 已完成的节点/阶段列表
        "running_list": get_running_task_list(task_id)  # 正在运行的节点/阶段列表
    }
    # 记录状态查询日志，方便追踪前端轮询情况
    logger.info(
        f"[{task_id}] 任务状态查询，当前状态：{task_status_info['status']}，已完成节点：{task_status_info['done_list']}")
    return task_status_info
