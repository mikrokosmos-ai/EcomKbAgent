from typing import List, Any, Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File
from app.core.logger import logger
from app.api.dependencies import get_import_pipeline
from app.api.schemas.import_schema import UploadResponse
from app.services.import_service import invoke_import_graph, save_upload_files

import_router = APIRouter(tags=["import"])
router = import_router  # 兼容旧命名，避免既有 import 失效


"""
    核心接口：多文件上传接口（不上传 MinIO）
    支持多文件批量上传，核心流程：接收文件 → 本地保存 → 启动后台任务
    访问地址：http://localhost:7000/upload （POST请求，form-data格式传参）
"""
@import_router.post(
    "/upload",
    summary="文件上传接口",
    description="支持多文件批量上传，自动触发知识库导入全流程",
    response_model=UploadResponse,
)
async def upload_files(
        background_tasks: BackgroundTasks,
        import_pipeline: Annotated[Any, Depends(get_import_pipeline)],
        files: List[UploadFile] = File(...)
):
    """
    文件上传核心接口（不上传 MinIO）
    1. 接收前端上传的多文件（PDF/MD为主）
    2. 按「日期/任务ID」分层保存到本地输出目录，避免文件冲突
       （目录构建 / 落盘 / 上传阶段标记已收纳到 app/services/import_service.save_upload_files）
    3. 为每个文件生成唯一TaskID，启动独立的LangGraph后台处理任务
    4. 实时更新任务状态，供前端轮询监控进度

    :param background_tasks: FastAPI后台任务对象，用于异步执行LangGraph流程
    :param import_pipeline: 已编译的导入 LangGraph 应用（依赖注入）
    :param files: 前端上传的文件列表（form-data格式）
    :return: 包含上传结果和所有任务ID的JSON响应
    """
    # 1. 落盘 + 生成任务ID（服务层负责：目录构建、文件保存、upload_file 阶段标记）
    uploaded_files = save_upload_files(files)
    task_ids = [task_id for task_id, _, _ in uploaded_files]

    # 2. 为每个文件登记 LangGraph 全流程后台任务（顺序与 files 一致）
    for task_id, task_local_dir, local_file_abs_path in uploaded_files:
        background_tasks.add_task(
            invoke_import_graph,
            task_id,
            task_local_dir,
            local_file_abs_path,
            import_pipeline
        )
        logger.info(f"[{task_id}] 已将LangGraph全流程加入后台任务，任务已启动")

    # 3. 所有文件处理完毕，返回上传成功信息和所有TaskID
    logger.info(f"多文件上传处理完毕，共处理{len(files)}个文件，生成TaskID列表：{task_ids}")
    return {
        "code": 200,
        "message": f"Files uploaded successfully, total: {len(files)}",
        "task_ids": task_ids
    }
