import uuid
from typing import Any, Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.logger import logger
from app.api.schemas.query_schema import QuerySchema
from app.api.schemas.history_schema import HistoryResponse
from app.api.dependencies import get_query_pipeline
from app.services.query_service import run_query_graph
from app.utils.task_utils import get_task_result, get_done_task_list
from app.utils.sse_utils import create_sse_queue, sse_generator
from app.repositories.history_repo import get_recent_messages, clear_history

query_router = APIRouter(tags=["query"])
router = query_router  # 兼容旧命名，避免既有 import 失效


# 接口二: /health 健康检查接口
@query_router.get("/health")
def health():
    logger.info(f"触发后台检测检查接口，数据一切正常!!")
    return {
        "ok": True
    }


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
@query_router.get("/history/{session_id}", response_model=HistoryResponse)
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
