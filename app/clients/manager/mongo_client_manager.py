"""
MongoDB 客户端管理器

统一创建和管理 MongoDB 客户端，服务于会话历史记录的读写。
"""
import logging
from typing import Optional

from pymongo import MongoClient

from app.conf.mongo_config import mongo_config


class HistoryMongoTool:
    """
    MongoDB 历史对话记录读写工具类 (基于原生 PyMongo 实现)
    核心功能：封装MongoDB的连接、集合初始化、索引创建，为上层提供统一的数据库操作入口
    """

    def __init__(self):
        try:
            # 从配置读取MongoDB连接地址（敏感配置，不硬编码）
            self.mongo_url = mongo_config.mongo_url
            # 从配置读取要使用的数据库名称
            self.db_name = mongo_config.db_name

            # 创建MongoDB客户端实例，建立与数据库的连接
            self.client = MongoClient(self.mongo_url)
            # 获取指定名称的数据库对象 user 库
            self.db = self.client[self.db_name]
            # 获取对话记录的集合（相当于关系型数据库的表），集合名：chat_message  db.chat_message
            self.chat_message = self.db["chat_message"]

            # 为chat_message集合创建复合索引，提升查询性能
            # 索引规则：session_id升序 + ts降序，适配"按会话查最新记录"的核心查询场景
            self.chat_message.create_index([("session_id", 1), ("ts", -1)])

            # 记录成功日志，确认数据库连接和初始化完成
            logging.info(f"Successfully connected to MongoDB: {self.db_name}")
        except Exception as e:
            # 捕获所有初始化异常，记录详细错误日志
            logging.error(f"Failed to connect to MongoDB: {e}")
            # 重新抛出异常，让调用方感知初始化失败，避免使用未初始化的实例
            raise


class MongoClientManager:
    def __init__(self, mongo_config):
        # 保存 MongoDB 配置，供 init() 时建立连接使用
        self.mongo_config = mongo_config
        # 先声明 client 为 None，真正的连接建立放到 init() 里
        self.client: Optional[HistoryMongoTool] = None

    def init(self):
        # 幂等：已初始化则直接返回，避免重复建连
        if self.client is not None:
            return
        # HistoryMongoTool 内部完成连接与索引初始化，失败会向上抛出
        self.client = HistoryMongoTool()

    def close(self):
        # 进程退出前关闭连接，释放网络资源
        if self.client is not None:
            self.client.client.close()
            self.client = None


# 全局可复用的 MongoDB 客户端管理器单例
mongo_client_manager = MongoClientManager(mongo_config)
