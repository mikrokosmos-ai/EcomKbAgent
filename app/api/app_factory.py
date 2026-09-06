from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.lifespan import lifespan
from app.api.routers.import_router import import_router
from app.api.routers.query_router import query_router
from app.api.routers.task_router import task_router


def create_app(include_import: bool = True, include_query: bool = True) -> FastAPI:
    """
    统一装配 FastAPI 应用：
    - CORS 跨域配置
    - 生命周期管理（lifespan 统一初始化/释放外部客户端）
    - 按需挂载 import / query 两个路由，并挂载统一的任务状态路由
    """
    app = FastAPI(
        title="EcomKbAgent",
        description="电商知识库导入与查询服务",
        lifespan=lifespan,
    )

    # 跨域配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 任务状态查询接口：import 与 query 共用同一实现，避免重复路由
    app.include_router(task_router)

    if include_import:
        app.include_router(import_router)
    if include_query:
        app.include_router(query_router)

    return app
