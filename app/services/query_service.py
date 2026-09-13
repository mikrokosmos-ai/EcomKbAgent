"""
查询服务层

把原先内联在 query_router 里的后台查询任务 run_query_graph 抽出
（函数体逐行迁自原路由）。

注意（改造文档 §8 C-3）：本函数**必须保持同步定义**。路由侧用
`starlette.concurrency.run_in_threadpool` 调用它以避免阻塞事件循环；
若改成 `async def`，线程池会拿到一个未被 await 的 coroutine，任务将静默失效。
"""
from app.core.logger import logger
from app.pipelines.query_pipeline.state import create_query_default_state
from app.utils.task_utils import (
    clear_task, update_task_status, get_task_result,
    TASK_STATUS_PROCESSING, TASK_STATUS_COMPLETED, TASK_STATUS_FAILED
)
from app.utils.sse_utils import SSEEvent, push_to_session


# 同步方法：执行查询图（graph 通过依赖注入传入，避免服务层直接持有编译对象）
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
