"""
Milvus 客户端管理器

统一创建和管理 Milvus 客户端，服务于知识库切片向量的写入与检索。
"""
from typing import Optional

from pymilvus import MilvusClient

from app.conf.milvus_config import milvus_config


class MilvusClientManager:
    def __init__(self, milvus_config):
        # 保存 Milvus 配置，init() 时按它建立连接
        self.milvus_config = milvus_config
        # 先声明 client 为 None，真正的连接建立放到 init() 里
        self.client: Optional[MilvusClient] = None

    def init(self):
        # 幂等：已初始化则直接返回，避免重复建连
        if self.client is not None:
            return
        # 地址为空时直接抛错，避免沿用现状"返回 None 让调用方崩溃"的隐式契约
        if not self.milvus_config.milvus_url:
            raise ValueError("Milvus 配置缺失：请在 .env 中配置 MILVUS_URL")
        self.client = MilvusClient(uri=self.milvus_config.milvus_url)

    def close(self):
        # MilvusClient 的连接释放是同步方法，这里不声明成 async
        if self.client is not None:
            self.client.close()
            self.client = None


# 全局可复用的 Milvus 客户端管理器单例
milvus_client_manager = MilvusClientManager(milvus_config)
