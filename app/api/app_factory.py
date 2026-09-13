from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.lifespan import lifespan
from app.core.logger import logger, PROJECT_ROOT
from app.api.routers.import_router import import_router
from app.api.routers.query_router import query_router
from app.api.routers.task_router import task_router


def create_app(
    include_import: bool = True,
    include_query: bool = True,
    mount_frontend: bool = None,
) -> FastAPI:
    """
    统一装配 FastAPI 应用：
    - CORS 跨域配置
    - 生命周期管理（lifespan 统一初始化/释放外部客户端）
    - 按需挂载 import / query 两个路由，并挂载统一的任务状态路由

    :param include_import: 是否挂载导入路由
    :param include_query: 是否挂载查询路由
    :param mount_frontend: 是否挂载前端 SPA。
        None（默认）表示"自动"——等价于改造前行为（仅 import + query 同时启用时挂载），
        因此不影响既有 all / 单服务模式的挂载语义；
        `both` 模式下由调用方显式指定（只给其中一个 app 传 True），避免两个 app 都不挂 SPA。
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
    # 默认（mount_frontend=None）：沿用改造前行为——仅 import + query 同时启用时挂载，避免拆分模式出现半残 SPA；
    # both 模式下两个 app 各启用一半，由调用方显式指定由哪个 app 挂载（见 main.py 与改造文档 §8 C-7）
    should_mount_frontend = (include_import and include_query) if mount_frontend is None else mount_frontend
    if should_mount_frontend:
        frontend_dist = PROJECT_ROOT / "frontend" / "dist"
        if frontend_dist.is_dir():
            app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
        else:
            logger.warning(f"前端构建产物不存在：{frontend_dist}，请先执行 `cd frontend && pnpm run build`")

    return app
