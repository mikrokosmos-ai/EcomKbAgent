"""
Reranker 客户端管理器

统一创建和管理本地 FlagReranker 重排模型，服务于查询结果的精排。
"""
from typing import Optional

from FlagEmbedding import FlagReranker

from app.conf.reranker_config import reranker_config


class RerankerClientManager:
    def __init__(self, reranker_config):
        # 保存 Reranker 配置，init() 时按它加载本地模型
        self.reranker_config = reranker_config
        # 先声明 client 为 None，真正的模型加载放到 init() 里
        self.client: Optional[FlagReranker] = None

    def init(self):
        # 幂等：已加载则直接返回
        if self.client is not None:
            return
        self.client = FlagReranker(
            model_name_or_path=self.reranker_config.bge_reranker_large,
            device=self.reranker_config.bge_reranker_device,
            use_fp16=self.reranker_config.bge_reranker_fp16,
        )

    def close(self):
        # 释放模型引用（显存回收交由 GC 与 torch 管理）
        self.client = None


# 全局可复用的 Reranker 客户端管理器单例
reranker_client_manager = RerankerClientManager(reranker_config)
