"""
Neo4j 客户端管理器

统一创建和管理 Neo4j driver，服务于知识图谱（实体 / 关系）的写入与查询。
结构与既有 6 个 manager 同构：init() 幂等建连、close() 释放。
"""
from typing import Optional

from neo4j import Driver, GraphDatabase

from app.conf.neo4j_config import neo4j_config


class Neo4jClientManager:
    def __init__(self, neo4j_config):
        # 保存 Neo4j 配置，init() 时按它建立 driver
        self.neo4j_config = neo4j_config
        # 先声明 driver 为 None，真正的连接建立放到 init() 里
        self.driver: Optional[Driver] = None

    def init(self):
        # 幂等：已初始化则直接返回，避免重复建连
        if self.driver is not None:
            return
        # 地址为空时直接抛错，避免沿用"返回 None 让调用方崩溃"的隐式契约
        if not self.neo4j_config.uri:
            raise ValueError("Neo4j 配置缺失：请在 .env 中配置 NEO4J_URI")
        # 用户名/密码均有值时才传 auth（否则传 None，兼容关闭鉴权的实例）
        auth = None
        if self.neo4j_config.username and self.neo4j_config.password:
            auth = (self.neo4j_config.username, self.neo4j_config.password)
        self.driver = GraphDatabase.driver(self.neo4j_config.uri, auth=auth)
        # 建连后立即校验连通性：失败向上抛出，由 lifespan 决定是否降级为"仅告警"
        self.driver.verify_connectivity()

    def close(self):
        if self.driver is not None:
            self.driver.close()
            self.driver = None


# 全局可复用的 Neo4j 客户端管理器单例
neo4j_client_manager = Neo4jClientManager(neo4j_config)
