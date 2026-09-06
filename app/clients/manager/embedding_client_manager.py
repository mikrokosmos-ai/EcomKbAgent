"""
Embedding 客户端管理器

统一创建和管理本地 BGE-M3 混合向量模型，服务于稠密+稀疏向量的生成。
"""
from typing import Optional

from pymilvus.model.hybrid import BGEM3EmbeddingFunction

from app.conf.embedding_config import embedding_config
from app.core.logger import logger


class EmbeddingClientManager:
    def __init__(self, embedding_config):
        # 保存 Embedding 配置，init() 时按它加载本地模型
        self.embedding_config = embedding_config
        # 先声明 client 为 None，真正的模型加载放到 init() 里
        self.client: Optional[BGEM3EmbeddingFunction] = None

    def init(self):
        # 幂等：已加载则直接返回，避免重复加载模型
        if self.client is not None:
            return

        model_name = self.embedding_config.bge_m3_path
        device = self.embedding_config.bge_device or "cpu"
        use_fp16 = self.embedding_config.bge_fp16 or False

        logger.info(
            "开始初始化BGE-M3模型",
            extra={
                "model_name": model_name,
                "device": device,
                "use_fp16": use_fp16,
                "normalize_embeddings": True,
            },
        )

        # 初始化BGE-M3模型，开启原生L2归一化（适配Milvus IP内积检索）
        try:
            self.client = BGEM3EmbeddingFunction(
                model_name=model_name,
                device=device,
                use_fp16=use_fp16,
                normalize_embeddings=True,
            )
            logger.success("BGE-M3模型初始化成功，已开启原生L2归一化")
        except Exception as e:
            logger.error(f"BGE-M3模型初始化失败：{str(e)}", exc_info=True)
            raise

    def close(self):
        # 释放模型引用（显存回收交由 GC 与 torch 管理）
        self.client = None

    def encode(self, texts):
        """
        为文本列表生成稠密+稀疏混合向量嵌入（模型原生L2归一化）
        :param texts: 要生成嵌入的文本列表，单文本也需封装为列表
        :return: 字典格式的向量结果，key为dense/sparse，对应嵌套列表/字典列表
        """
        # 入参合法性校验
        if not isinstance(texts, list) or len(texts) == 0:
            logger.warning("生成向量入参不合法，texts必须为非空列表")
            raise ValueError("参数texts必须是包含文本的非空列表")

        logger.info(f"开始为{len(texts)}条文本生成混合向量嵌入")
        try:
            # 加载模型（未初始化则触发懒加载）
            if self.client is None:
                self.init()
            # 模型编码生成向量，返回dense（稠密向量）+sparse（CSR格式稀疏向量）
            embeddings = self.client.encode_documents(texts)

            # 把模型输出的 CSR 稀疏矩阵，按"每条文本一行"拆成 {特征索引: 权重} 字典
            processed_sparse = []
            for i in range(len(texts)):
                sparse_indices = embeddings["sparse"].indices[
                    embeddings["sparse"].indptr[i]:embeddings["sparse"].indptr[i + 1]
                ].tolist()
                sparse_data = embeddings["sparse"].data[
                    embeddings["sparse"].indptr[i]:embeddings["sparse"].indptr[i + 1]
                ].tolist()
                sparse_dict = {k: v for k, v in zip(sparse_indices, sparse_data)}
                processed_sparse.append(sparse_dict)

            result = {
                "dense": [emb.tolist() for emb in embeddings["dense"]],
                "sparse": processed_sparse,
            }
            logger.success(f"{len(texts)}条文本向量生成完成，格式已适配工业级使用")
            return result
        except Exception as e:
            logger.error(f"文本向量生成失败：{str(e)}", exc_info=True)
            raise  # 不吞异常，向上传递让调用方做重试/降级处理


# 全局可复用的 Embedding 客户端管理器单例
embedding_client_manager = EmbeddingClientManager(embedding_config)
