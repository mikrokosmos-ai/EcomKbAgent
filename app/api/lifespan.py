"""
FastAPI 应用生命周期管理

负责在服务启动时初始化外部客户端，在服务关闭时释放连接资源。
分级策略：Milvus / MongoDB 为必需依赖，失败即阻断启动；MinIO / Embedding / Reranker
为可选依赖，失败仅告警；Embedding / Reranker 的本地模型加载由 WARMUP_ENABLE 控制，
默认关闭以保持与原懒加载行为一致。
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients.manager.embedding_client_manager import embedding_client_manager
from app.clients.manager.milvus_client_manager import milvus_client_manager
from app.clients.manager.minio_client_manager import minio_client_manager
from app.clients.manager.mongo_client_manager import mongo_client_manager
from app.clients.manager.reranker_client_manager import reranker_client_manager
from app.core.logger import logger

# 本地模型预热开关：默认关闭，与原有懒加载行为保持一致
WARMUP_ENABLE = os.getenv("WARMUP_ENABLE", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理应用启动和关闭两个阶段的外部资源"""

    # 启动阶段：必需项，失败直接让服务启动失败，避免带着坏状态对外提供服务
    milvus_client_manager.init()
    mongo_client_manager.init()

    # 启动阶段：可选项，失败只记录告警，保证服务仍可对外提供部分能力
    try:
        minio_client_manager.init()
    except Exception as e:
        logger.warning(f"[minio] 客户端预热失败，相关功能将不可用：{e}")

    if WARMUP_ENABLE:
        for name, manager in (
            ("embedding", embedding_client_manager),
            ("reranker", reranker_client_manager),
        ):
            try:
                manager.init()
            except Exception as e:
                logger.warning(f"[{name}] 客户端预热失败，相关功能将不可用：{e}")

    # yield 之前是启动逻辑，yield 之后是关闭逻辑；中间阶段由 FastAPI 正常处理请求
    yield

    # 关闭阶段：统一释放外部连接，避免进程退出前留下未关闭的网络连接
    milvus_client_manager.close()
    mongo_client_manager.close()
