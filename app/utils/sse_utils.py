import json
import queue
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from fastapi import Request

from app.core.logger import logger


class SSEEvent:
    READY = "ready"         # 连接建立
    PROGRESS = "progress"   # 任务节点进度
    DELTA = "delta"         # LLM 流式输出增量
    FINAL = "final"         # 最终完整答案
    ERROR = "error"         # 错误信息
    CLOSE = "__close__"     # 关闭连接信号


# 全局 SSE 会话队列存储
# Key: session_id, Value: queue.Queue
_session_stream: Dict[str, queue.Queue] = {}

def get_sse_queue(session_id: str) -> Optional["queue.Queue"]:
    """获取指定 session 的队列"""
    return _session_stream.get(session_id)


def create_sse_queue(session_id: str) -> "queue.Queue":
    """创建并注册一个新的 SSE 队列"""
    logger.info(f"[SSE] 创建队列，会话={session_id}")
    q = queue.Queue()
    _session_stream[session_id] = q
    return q


def remove_sse_queue(session_id: str):
    """移除指定 session 的队列"""
    logger.info(f"[SSE] 移除队列，会话={session_id}")
    _session_stream.pop(session_id, None)


def _sse_pack(event: str, data: Dict[str, Any]) -> str:
    """打包 SSE 消息格式"""
    payload = json.dumps(data, ensure_ascii=False)
    # print(f"[SSE] Packing event: {event}, payload: {payload[:50]}...")
    return f"event: {event}\ndata: {payload}\n\n"


def push_to_session(session_id: str, event: str, data: Dict[str, Any]):
    """
    通过 session_id 推送事件
    """
    stream_queue = get_sse_queue(session_id)
    if stream_queue:
        # print(f"[SSE] Pushing to session {session_id}: {event}")
        stream_queue.put({"event": event, "data": data})
    else:
        logger.warning(f"[SSE] 未找到会话队列，事件丢弃：会话={session_id}，事件={event}")


async def sse_generator(session_id: str, request: Request):
    """
    SSE 生成器，用于 FastAPI 的 StreamingResponse
    """
    logger.info(f"[SSE] 生成器启动，会话={session_id}")
    stream_queue = get_sse_queue(session_id)
    if stream_queue is None:
        # 如果没有对应的队列，直接结束
        logger.warning(
            f"[SSE] 未找到会话队列，生成器直接结束：会话={session_id}，"
            f"当前存活会话={list(_session_stream.keys())}"
        )
        return

    loop = asyncio.get_running_loop()
    try:
        # 发送连接建立信号
        logger.debug(f"[SSE] 发送 ready 信号，会话={session_id}")
        yield _sse_pack("ready", {})

        while True:
            # 若客户端断开，尽快退出
            if await request.is_disconnected():
                logger.info(f"[SSE] 客户端已断开连接，会话={session_id}")
                break

            try:
                # 使用 run_in_executor 避免阻塞 async 事件循环
                # {event:"process" : data: {任务状态 / 已完成节点 / 进行中节点}}
                msg = await loop.run_in_executor(None, stream_queue.get, True, 1.0)
            except queue.Empty:
                # print(f"[SSE] Queue empty for {session_id}, waiting...")
                continue

            event = msg.get("event")
            data = msg.get("data")

            logger.debug(f"[SSE] 推送事件，会话={session_id}，事件={event}")

            # 特殊关闭事件
            if event == "__close__":
                logger.info(f"[SSE] 收到关闭信号，结束生成器，会话={session_id}")
                break

            yield _sse_pack(event, data)
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        logger.info(f"[SSE] 客户端连接中断（取消/重置/管道破裂），会话={session_id}")
        # 生成器被取消/对端断开：静默退出
        return
    except Exception:
        # 生成器内出现预期外异常：保留完整堆栈，避免只留一行 message 难以定位
        logger.exception(f"[SSE] 生成器运行异常，会话={session_id}")
    finally:
        logger.info(f"[SSE] 生成器结束，会话={session_id}")
        # 清理资源
        remove_sse_queue(session_id)