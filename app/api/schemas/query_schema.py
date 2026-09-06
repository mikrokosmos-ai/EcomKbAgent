"""
查询接口请求体定义

集中声明 API 层输入输出的数据结构，让路由函数只处理业务流程，
字段校验和 OpenAPI 文档生成交给 Pydantic 与 FastAPI 完成。
"""
import re

from pydantic import BaseModel, Field, field_validator


class QuerySchema(BaseModel):
    """查询请求数据结构"""
    query: str = Field(..., description="查询内容")
    session_id: str | None = Field(None, description="会话ID")
    is_stream: bool = Field(False, description="是否流式返回")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query 不能为空")
        if len(v) > 2000:
            raise ValueError("query 长度超过上限 2000")
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None):
        # session_id 为空时后端会生成新会话，因此必须允许 None
        if v is None:
            return v
        v = v.strip()
        # 只接受字母数字和短横线，防止任意字符进入 SSE 队列 key 与 Mongo 查询
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", v):
            raise ValueError("session_id 格式非法")
        return v


# 兼容旧命名，避免历史 import 失效
QueryRequest = QuerySchema
