from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.lifespan import lifespan
from app.core.logger import logger, PROJECT_ROOT
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

    # 挂载前端构建产物（需先 `cd frontend && pnpm run build` 产出 dist/）
    # 挂在所有 API 路由之后：API 优先匹配；html=True 让 "/" 直接返回 index.html
    # 仅 all 模式（import + query 同时启用）挂载，避免拆分模式下出现半残 SPA
    if include_import and include_query:
        frontend_dist = PROJECT_ROOT / "frontend" / "dist"
        if frontend_dist.is_dir():
            app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
        else:
            logger.warning(f"前端构建产物不存在：{frontend_dist}，请先执行 `cd frontend && pnpm run build`")

    return app
