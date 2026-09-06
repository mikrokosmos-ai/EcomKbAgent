from pathlib import Path
import uuid
from typing import Any, Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from mimetypes import guess_type
from starlette.concurrency import run_in_threadpool

from app.core.logger import logger, PROJECT_ROOT
from app.api.schemas.query_schema import QuerySchema
from app.api.dependencies import get_query_pipeline
from app.pipelines.query_pipeline.state import create_query_default_state
from app.utils.task_utils import (
    clear_task, update_task_status, get_task_result, get_done_task_list,
    TASK_STATUS_PROCESSING, TASK_STATUS_COMPLETED, TASK_STATUS_FAILED
)
from app.utils.sse_utils import create_sse_queue, SSEEvent, sse_generator, push_to_session
from app.repositories.history_repo import get_recent_messages, clear_history

query_router = APIRouter(tags=["query"])
router = query_router  # 兼容旧命名，避免既有 import 失效


# 接口1: 返回html页面
@query_router.get("/")
def index():
    return return_query_html()


@query_router.get("/query/html")
def return_query_html():
    # 1.拼接地址
    html_path_obj = PROJECT_ROOT / "web" / "chat.html"
    # 2.判断文件是否存在
    if not html_path_obj.exists():
        logger.error(f"html不存在,无法返回页面!")
        raise HTTPException(status_code=404, detail=f"html不存在,无法返回页面!")
    # 3.响应文件数据
    return FileResponse(
        path=html_path_obj,
        media_type=guess_type(html_path_obj.name)[0]
    )


# 接口二: /health 健康检查接口
@query_router.get("/health")
def health():
    logger.info(f"触发后台检测检查接口，数据一切正常!!")
    return {
        "ok": True
    }


# 同步方法：执行查询图（graph 通过依赖注入传入，避免路由层直接持有编译对象）
def run_query_graph(session_id: str, query: str, is_stream: bool, graph):
    """执行query graph"""
    try:
        # 清空原有的任务列表
        clear_task(session_id)

        # 更新新状态
        update_task_status(session_id, TASK_STATUS_PROCESSING, is_stream)

        # 再执行
        initial_state = (create_query_default_state(
            session_id=session_id,
            original_query=query,
            is_stream=is_stream
        ))
        state = graph.invoke(initial_state)
        update_task_status(session_id, TASK_STATUS_COMPLETED, is_stream)

        # final事件一定最后推送, 因为他会关闭本次流
        image_urls = state['image_urls']
        push_to_session(
            session_id,
            SSEEvent.FINAL,
            {
                "answer": get_task_result(session_id, "answer"),
                "status": "completed",
                "image_urls": image_urls
            }
        )
    except Exception as e:
        logger.exception(f"执行{session_id}对应查询问题:{query},任务执行失败! 错误信息:{str(e)}")
        update_task_status(session_id, TASK_STATUS_FAILED, is_stream)
        # 推送指定类型的事件
        push_to_session(session_id, SSEEvent.ERROR, {"error": str(e)})


# 接口三: 前端提问查询接口
@query_router.post("/query")
async def query(
    query_request: QuerySchema,
    backgroundtasks: BackgroundTasks,
    query_pipeline: Annotated[Any, Depends(get_query_pipeline)],
):
    is_stream = query_request.is_stream
    session_id = query_request.session_id or str(uuid.uuid4())
    query_text = query_request.query
    # 判定是否异步执行(流式)
    if is_stream:
        # 异步流式 ,创建session_id对应的队列
        create_sse_queue(session_id)  # [sse -> queue ]
        # 是 添加到异步任务中..
        backgroundtasks.add_task(run_query_graph, session_id, query_text, is_stream, query_pipeline)
        logger.info(f"query;{query_text}已经开启异步和流式处理!!")
        # 立即返回结果
        return {"message": "结果正在处理中...", "session_id": session_id}
    else:
        # 否,同步执行，但放到线程池避免阻塞事件循环
        await run_in_threadpool(run_query_graph, session_id, query_text, is_stream, query_pipeline)
        # 获取结果
        answer = get_task_result(session_id, "answer")
        logger.info(f"query;{query_text}已经开启同步处理!，处理结果为：{answer}!")
        # 等待结束以后,返回结果
        return {"message": "处理完成！",
                "session_id": session_id,
                "answer": answer,
                "done_list": get_done_task_list(session_id)}


# 接口四: 流式获取结果
@query_router.get("/stream/{session_id}")
async def stream_query_result(session_id: str, request: Request):
    logger.info(f"session_id = {session_id}客户端，已经和后台建立了长链接")
    return StreamingResponse(
        # 生成器 函数 yield
        sse_generator(session_id, request),
        # 返回结果类型
        media_type="text/event-stream"
    )


# 接口五: 查询历史聊天记录
@query_router.get("/history/{session_id}")
def get_history(session_id: str, limit: int = 10):
    records = get_recent_messages(session_id, limit=limit)
    items = []
    for r in records:
        items.append({
            "_id": str(r.get("_id")) if r.get("_id") is not None else "",
            "session_id": r.get("session_id", ""),
            "role": r.get("role", ""),
            "text": r.get("text", ""),
            "rewritten_query": r.get("rewritten_query", ""),
            "item_names": r.get("item_names", []),
            "ts": r.get("ts")
        })
    return {
        "session_id": session_id,
        "items": items
    }


# 接口六: 清空历史聊天记录
@query_router.delete("/history/{session_id}")
def delete_history(session_id: str):
    # 删除
    delete_count = clear_history(session_id)
    return {
        "message": f"删除:{session_id}会话对应的聊天记录成功!!",
        "delete_count": delete_count
    }
