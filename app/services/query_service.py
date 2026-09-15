"""
查询服务层

把原先内联在 query_router 里的后台查询任务 run_query_graph 抽出
（函数体逐行迁自原路由）。

ID 语义（§I-11 task_id / session_id 分离）：
- task_id：SSE 队列 key + 任务追踪 key（唯一追踪维度，支持同会话并发多轮查询）
- session_id：Mongo 会话历史归集键（仅用于落库/取历史与日志）
"""
from app.core.logger import logger
from app.pipelines.query_pipeline.state import create_query_default_state
from app.utils.task_utils import (
    clear_task, update_task_status, get_task_result,
    TASK_STATUS_PROCESSING, TASK_STATUS_COMPLETED, TASK_STATUS_FAILED
)
from app.utils.sse_utils import SSEEvent, push_to_session


# 同步方法：执行查询图（graph 通过依赖注入传入，避免服务层直接持有编译对象）
def run_query_graph(task_id: str, session_id: str, query: str, is_stream: bool, graph):
    """执行query graph"""
    try:
        # 清空原有的任务列表（按 task_id：并发查询之间互不干扰）
        clear_task(task_id)

        # 更新新状态
        update_task_status(task_id, TASK_STATUS_PROCESSING, is_stream)

        # 再执行
        initial_state = (create_query_default_state(
            session_id=session_id,
            task_id=task_id,
            original_query=query,
            is_stream=is_stream
        ))
        state = graph.invoke(initial_state)
        update_task_status(task_id, TASK_STATUS_COMPLETED, is_stream)

        # final事件一定最后推送, 因为他会关闭本次流
        image_urls = state['image_urls']
        push_to_session(
            task_id,
            SSEEvent.FINAL,
            {
                "answer": get_task_result(task_id, "answer"),
                "status": "completed",
                "image_urls": image_urls
            }
        )
    except Exception as e:
        logger.exception(f"执行{session_id}对应查询问题:{query},任务执行失败! 错误信息:{str(e)}")
        update_task_status(task_id, TASK_STATUS_FAILED, is_stream)
        # 推送指定类型的事件
        push_to_session(task_id, SSEEvent.ERROR, {"error": str(e)})
