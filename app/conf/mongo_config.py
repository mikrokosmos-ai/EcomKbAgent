# 导入核心依赖：数据类、环境变量读取
from dataclasses import dataclass
import os
from dotenv import load_dotenv

# 提前加载.env配置文件（保持和原代码一致，只需执行一次）
load_dotenv()


# 定义MongoDB会话历史存储配置
@dataclass
class MongoConfig:
    mongo_url: str    # MongoDB连接地址（含协议、主机、端口）
    db_name: str      # 会话历史使用的数据库名称


# 实例化Mongo配置对象，从.env读取并绑定
mongo_config = MongoConfig(
    mongo_url=os.getenv("MONGO_URL"),
    db_name=os.getenv("MONGO_DB_NAME")
)
