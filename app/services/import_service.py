"""
导入服务层

把原先内联在 import_router 里的两类逻辑抽出：
    1. 后台任务 invoke_import_graph —— LangGraph 全流程执行（函数体逐行迁自原路由）
    2. 上传落盘 save_upload_files —— 目录构建 / 文件保存 / upload_file 阶段标记
使路由退化为"参数绑定 + 调用服务 + 返回响应"。
"""
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from fastapi import UploadFile

from app.core.logger import logger, PROJECT_ROOT
from app.pipelines.import_pipeline.state import get_default_state
from app.utils.task_utils import (
    update_task_status, add_done_task, add_running_task
)


def invoke_import_graph(task_id: str, local_dir: str, local_file_path: str, graph):
    """
       LangGraph全流程执行后台任务
       核心流程：初始化状态 → 流式执行图节点 → 实时更新任务状态 → 异常捕获
       任务状态更新：pending → processing → completed/failed
       节点进度更新：每完成一个节点，将节点名加入done_list，供前端轮询查看

       :param task_id: 全局唯一任务ID，关联单个文件的全流程处理
       :param local_dir: 该任务的本地文件存储目录（含临时文件/解析结果）
       :param local_file_path: 上传文件的本地绝对路径
       :param graph: 已编译的导入 LangGraph 应用（通过依赖注入传入）
       """
    try:
        # 1. 更新任务全局状态为：处理中
        update_task_status(task_id, "processing")
        logger.info(f"[{task_id}] 开始执行LangGraph全流程，本地文件路径：{local_file_path}")

        # 2. 初始化LangGraph状态：加载默认状态 + 注入当前任务的核心参数
        init_state = get_default_state()
        init_state["task_id"] = task_id  # 任务ID关联
        init_state["local_dir"] = local_dir  # 任务本地目录
        init_state["local_file_path"] = local_file_path  # 上传文件本地路径

        # 3. 流式执行LangGraph全流程（stream模式：实时获取每个节点的执行结果）
        for event in graph.stream(init_state):
            for node_name, node_result in event.items():
                # 记录每个节点完成的日志，包含任务ID和节点名，方便追踪执行顺序
                logger.info(f"[{task_id}] LangGraph节点执行完成：{node_name}")
                # 将完成的节点名加入【已完成列表】，前端轮询/status/{task_id}可实时获取
                add_done_task(task_id, node_name)

        # 4. 全流程执行完成，更新任务全局状态为：已完成
        update_task_status(task_id, "completed")
        logger.info(f"[{task_id}] LangGraph全流程执行完毕，任务完成")

    except Exception as e:
        # 5. 捕获全流程异常，更新任务全局状态为：失败，并记录错误日志（含堆栈）
        update_task_status(task_id, "failed")
        logger.error(f"[{task_id}] LangGraph全流程执行失败，异常信息：{str(e)}", exc_info=True)


def save_upload_files(files: List[UploadFile]) -> List[Tuple[str, str, str]]:
    """
    把上传的多文件按「日期 / 任务ID」分层落盘，并为每个文件生成唯一的任务ID。

    逐文件流程（与改造前的路由内联逻辑一致）：
        生成 task_id → 标记 upload_file 运行中 → 建目录 → 保存文件 → 标记 upload_file 已完成

    :param files: 前端上传的文件列表（form-data）
    :return: [(task_id, 本地目录, 文件绝对路径), ...]，顺序与 files 一致，供路由登记后台任务
    """
    # 1. 构建本地存储根目录：项目根目录/output/YYYYMMDD（按日期分层，方便管理）
    today_str = datetime.now().strftime("%Y%m%d")
    date_based_root_dir: Path = PROJECT_ROOT / "output" / today_str

    uploaded: List[Tuple[str, str, str]] = []

    # 2. 遍历处理每个上传的文件（多文件批量处理，各自独立生成TaskID）
    for file in files:
        # 生成全局唯一TaskID（UUID4），作为单个文件的全流程标识
        task_id = str(uuid.uuid4())
        logger.info(f"[{task_id}] 开始处理上传文件，文件名：{file.filename}，文件类型：{file.content_type}")

        # 3. 标记「文件上传」阶段为「运行中」，前端轮询可查
        add_running_task(task_id, "upload_file")

        # 4. 构建该任务的本地独立目录：output/YYYYMMDD/TaskID，避免多文件重名冲突
        task_local_dir: Path = date_based_root_dir / task_id
        task_local_dir.mkdir(parents=True, exist_ok=True)

        # 5. 构建上传文件的本地保存绝对路径
        local_file_abs_path: Path = task_local_dir / file.filename

        # 6. 将上传的文件保存到本地临时目录
        with local_file_abs_path.open("wb") as file_buffer:
            shutil.copyfileobj(file.file, file_buffer)
        logger.info(f"[{task_id}] 文件已保存至本地，路径：{local_file_abs_path}")

        # 7. 标记「文件上传」阶段为「已完成」
        add_done_task(task_id, "upload_file")

        uploaded.append((task_id, str(task_local_dir), str(local_file_abs_path)))

    return uploaded
