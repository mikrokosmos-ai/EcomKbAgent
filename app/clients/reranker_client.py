"""
Reranker 客户端门面
"""
from app.clients.manager.reranker_client_manager import reranker_client_manager


def get_reranker_model():
    """获取 FlagReranker 模型；若尚未初始化则触发一次懒加载兜底"""
    if reranker_client_manager.client is None:
        reranker_client_manager.init()
    return reranker_client_manager.client
