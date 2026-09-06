"""
FastAPI 依赖组装

集中声明 API 层需要的依赖函数，把 Client 和已编译的 Pipeline 按职责组装起来。
路由层只通过 Depends 声明自己需要什么对象，具体创建细节都收敛在这里，避免
HTTP 处理函数直接感知底层基础设施。
"""
from app.clients.manager.milvus_client_manager import milvus_client_manager
from app.clients.manager.mongo_client_manager import mongo_client_manager
from app.pipelines.import_pipeline.graph import kb_import_app
from app.pipelines.query_pipeline.graph import query_app


async def get_milvus_client():
    """获取应用启动阶段初始化好的 Milvus 客户端"""
    return milvus_client_manager.client


async def get_mongo_client():
    """获取应用启动阶段初始化好的 MongoDB 客户端"""
    return mongo_client_manager.client


async def get_query_pipeline():
    """获取已编译的查询 LangGraph 应用"""
    return query_app


async def get_import_pipeline():
    """获取已编译的导入 LangGraph 应用"""
    return kb_import_app
