# 导入核心依赖：数据类、环境变量读取
from dataclasses import dataclass
import os
from dotenv import load_dotenv

# 提前加载.env配置文件（保持和原代码一致，只需执行一次）
load_dotenv()


# 定义Neo4j图数据库配置（知识图谱：实体与关系的存储）
@dataclass
class Neo4jConfig:
    uri: str        # 连接地址（bolt://host:7687）
    username: str   # 认证用户名
    password: str   # 认证密码
    database: str   # 目标数据库名（Neo4j Community 版固定为 neo4j）


# 实例化Neo4j配置对象，从.env读取并绑定
neo4j_config = Neo4jConfig(
    uri=os.getenv("NEO4J_URI"),
    username=os.getenv("NEO4J_USER"),
    password=os.getenv("NEO4J_PASSWORD"),
    database=os.getenv("NEO4J_DATABASE", "neo4j")
)
