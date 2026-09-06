"""
Embedding 客户端门面

"""
from app.clients.manager.embedding_client_manager import embedding_client_manager


def get_bge_m3_ef():
    """获取 BGE-M3 模型单例；若尚未初始化则触发一次懒加载兜底"""
    if embedding_client_manager.client is None:
        embedding_client_manager.init()
    return embedding_client_manager.client


def generate_embeddings(texts):
    """
    为文本列表生成稠密+稀疏混合向量嵌入（模型原生L2归一化）
    :param texts: 要生成嵌入的文本列表，单文本也需封装为列表
    :return: 字典格式的向量结果，key为dense/sparse，对应嵌套列表/字典列表
    """
    return embedding_client_manager.encode(texts)
