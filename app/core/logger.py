"""
项目日志工具类
基于loguru实现，支持.env配置控制台/文件双输出，自动生成logs/app_年月日.log
特性：
1. 配置驱动：通过.env开关输出、修改日志级别
2. 自动路径：文件日志默认输出到 项目根/logs/app_YYYYMMDD.log
3. 自动清理：按配置保留日志，自动删除过期文件
4. 中文友好：utf-8编码，彻底解决中文乱码
5. 异步安全：开启异步入队，支持多线程/异步场景，避免日志错乱
6. 开箱即用：项目所有模块直接导入logger即可使用
7. 位置终极精准：穿透loguru内部+工具类自身，完美显示业务模块实际调用位置
"""
import sys
import inspect
from pathlib import Path
import os
from dotenv import load_dotenv
from loguru import logger

# 领域异常基类：@node_guard 用它对节点异常做统一归一化。
# 依赖方向：core.exceptions 只依赖标准库，因此此处不会形成循环导入。
from app.core.exceptions import AppError


# -------------------------- 第一步：加载.env配置文件 --------------------------
load_dotenv()

# -------------------------- 第二步：读取.env配置（带默认值，防止配置缺失） --------------------------
LOG_CONSOLE_ENABLE = os.getenv("LOG_CONSOLE_ENABLE", "True").lower() == "true"
LOG_CONSOLE_LEVEL = os.getenv("LOG_CONSOLE_LEVEL", "INFO").upper()
LOG_FILE_ENABLE = os.getenv("LOG_FILE_ENABLE", "True").lower() == "true"
LOG_FILE_LEVEL = os.getenv("LOG_FILE_LEVEL", "INFO").upper()
LOG_FILE_RETENTION = os.getenv("LOG_FILE_RETENTION", "7 days")

# -------------------------- 第三步：定义日志路径（自动推导项目根） --------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE_NAME = "app_{time:YYYYMMDD}.log"
LOG_FILE_PATH = LOG_DIR / LOG_FILE_NAME

# -------------------------- 第四步：定义日志格式（彩色、结构化、易读） --------------------------
LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name: <20}</cyan>:<cyan>{function: <15}</cyan>:<cyan>{line: <4}</cyan> - "
    "<level>{message}</level>"
)

# -------------------------- 第五步：初始化日志配置（核心方法） --------------------------
def init_logger():
    """
    初始化全局日志配置
    1. 移除loguru默认控制台输出（避免重复打印）
    2. 根据.env配置开启/关闭控制台输出
    3. 根据.env配置开启/关闭文件输出（自动创建logs文件夹）
    4. 配置日志格式、级别、分割、保留策略
    :return: 配置完成的loguru logger实例
    """
    # 1. 移除loguru默认的控制台输出
    logger.remove()

    # 2. 配置控制台输出（若.env开启）
    if LOG_CONSOLE_ENABLE:
        logger.add(
            sink=sys.stdout,
            level=LOG_CONSOLE_LEVEL,
            format=LOG_FORMAT,
            colorize=True,
            enqueue=True
        )

    # 3. 配置文件输出（若.env开启）
    if LOG_FILE_ENABLE:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.add(
            sink=LOG_FILE_PATH,
            level=LOG_FILE_LEVEL,
            format=LOG_FORMAT,
            rotation="00:00",
            retention=LOG_FILE_RETENTION,
            encoding="utf-8",
            enqueue=True,
            backtrace=True,
            diagnose=True
        )

    return logger

# -------------------------- 第六步：初始化并终极修正全局logger --------------------------
base_logger = init_logger()

def fix_log_position(record):
    """遍历调用栈，跳过loguru内部帧+工具类自身帧，提取业务代码实际调用位置"""
    for frame in inspect.stack():
        # 终极过滤：排除loguru内部 + 排除工具类logger.py自身，直接定位业务模块
        if ("_logger.py" in frame.filename or frame.function == "_log") or "logger.py" in frame.filename:
            continue
        # 更新日志字段为业务代码实际位置
        record.update(
            name=frame.filename.split("/")[-1].split("\\")[-1],
            function=frame.function,
            line=frame.lineno
        )
        break

# 应用终极修复，导出全局可用的logger
logger = base_logger.patch(fix_log_position)


from functools import wraps
import time
from typing import Mapping

def _trace_id(state) -> str:
    if isinstance(state, Mapping):
        return str(state.get("session_id") or state.get("task_id") or "-")
    return "-"

def node_log(node_name: str):
    """
    节点日志装饰器

    作用：
        自动打印节点的「开始 / 完成（含耗时）/ 异常（含堆栈）」，并按追踪ID聚合，
        让一次请求的节点执行链路在日志里连续可读。不吞异常，保持原有业务语义。

    同步 / 异步双分支（重要）：
        若被装饰函数是协程函数，必须走 async 分支。
        否则同步 wrapper 调用协程函数只会拿到一个 coroutine 对象——既不会真正执行，
        也不会把内部异常暴露出来，日志会错误地打印"节点完成"，异常则推迟到调用方 await 时才抛出。
        当前项目节点均为同步函数，此分支为**防御性实现**：
        保证后续引入异步节点时，本装饰器不会成为静默失效的陷阱。

    :param node_name: 节点名，用于日志前缀
    :return: 装饰器
    """
    def deco(func):
        # ---- 异步节点分支：必须 await，否则协程不会被真正执行 ----
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(state, *args, **kwargs):
                trace_id = _trace_id(state)
                start_ts = time.time()
                logger.info(f"[{node_name}] 节点开始，追踪ID={trace_id}")
                try:
                    result = await func(state, *args, **kwargs)
                    cost_ms = int((time.time() - start_ts) * 1000)
                    logger.info(f"[{node_name}] 节点完成，追踪ID={trace_id}，耗时={cost_ms}ms")
                    return result
                except Exception:
                    logger.exception(f"[{node_name}] 节点异常，追踪ID={trace_id}")
                    raise
            return async_wrapper

        # ---- 同步节点分支（当前项目全部节点走这里）----
        @wraps(func)
        def wrapper(state, *args, **kwargs):
            trace_id = _trace_id(state)
            start_ts = time.time()
            logger.info(f"[{node_name}] 节点开始，追踪ID={trace_id}")
            try:
                result = func(state, *args, **kwargs)
                cost_ms = int((time.time() - start_ts) * 1000)
                logger.info(f"[{node_name}] 节点完成，追踪ID={trace_id}，耗时={cost_ms}ms")
                return result
            except Exception:
                logger.exception(f"[{node_name}] 节点异常，追踪ID={trace_id}")
                raise
        return wrapper
    return deco

def step_log(step_name: str):
    """
    步骤日志装饰器：
    - 自动打印 步骤开始 / 步骤完成 / 步骤异常（含堆栈）
    - 不吞异常，保持原有业务语义
    """
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_ts = time.time()
            logger.info(f"[{step_name}] 步骤开始")
            try:
                result = func(*args, **kwargs)
                cost_ms = int((time.time() - start_ts) * 1000)
                logger.info(f"[{step_name}] 步骤完成，耗时={cost_ms}ms")
                return result
            except Exception:
                logger.exception(f"[{step_name}] 步骤异常")
                raise
        return wrapper
    return deco


def node_guard(node_name: str):
    """
    节点异常归一化装饰器

    作用：
        把节点内抛出的任意异常统一包装为 AppError，并自动带上节点名与根因，
        使上层可以按异常类型分支处理（如 except MilvusError 重试），
        而不必再去匹配错误字符串；同时让"是哪个节点挂的"直接体现在异常对象上。

    定序约定（重要，请勿写反）：
        源码自上而下书写为：
            @node_guard("node_xxx")
            @node_log("node_xxx")
            def node_xxx(state): ...
        Python 装饰器自下而上应用，因此 @node_log 会先包裹原函数
        （打印开始/完成/耗时，并在异常时用 logger.exception 记录**原始堆栈**后原样 re-raise），
        @node_guard 再包裹一层做归一化。
        最终效果：日志里保留原始异常的完整堆栈，而对上层抛出的是归一化后的领域异常。
        若两者顺序写反，日志中看到的将是 AppError 的堆栈，反而丢失根因信息。

    幂等：
        若节点内部已经抛出 AppError，则直接透传，不会被二次包装覆盖最初的 node_name。

    async 兼容：
        若被装饰函数是协程函数，则返回 async wrapper。
        当前项目的节点均为同步函数（异步能力封装在节点内部用 asyncio.run 调用），
        此处预留异步分支，便于后续引入真正的异步节点时无需改动本装饰器。

    使用示例:
        @node_guard("node_rerank")
        @node_log("node_rerank")
        def node_rerank(state):
            ...

    :param node_name: 节点名，会写入被包装异常的 node_name 字段
    :return: 装饰器
    """
    def deco(func):
        # ---- 异步节点分支：保持协程语义，避免同步 wrapper 把结果变成 coroutine ----
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except AppError:
                    # 已是领域异常：透传，保留最初的节点名与根因
                    raise
                except Exception as e:
                    raise AppError.wrap(e, node_name=node_name) from e
            return async_wrapper

        # ---- 同步节点分支（当前项目全部节点走这里）----
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except AppError:
                raise
            except Exception as e:
                raise AppError.wrap(e, node_name=node_name) from e
        return wrapper
    return deco

# -------------------------- 测试代码（验证修复效果） --------------------------
if __name__ == '__main__':
    logger.info("【测试】logger.py内部调用（仅测试，业务模块调用会显示正确文件名）")
    print(f"日志文件输出路径：{LOG_FILE_PATH}")
    logger.error("【测试】logger.py内部调用（仅测试，业务模块调用会显示正确文件名）")

    # 异常堆栈演示：logger.exception() 需要放在 except 代码块中
    try:
        # 伪代码：模拟业务异常（例如数据库查询、网络调用、文件解析等）
        result = 10 / 0
        logger.info(f"业务结果：{result}")
    except Exception:
        logger.exception("【测试】捕获到业务异常，输出完整堆栈信息")
