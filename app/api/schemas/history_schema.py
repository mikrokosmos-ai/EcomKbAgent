"""
查询历史接口的响应体定义

集中声明 GET /history/{session_id} 的返回结构，供路由的 response_model 使用。

"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class HistoryItem(BaseModel):
    """单条聊天历史记录"""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default="", alias="_id", description="记录ID（对应 Mongo 的 _id）")
    session_id: str = Field(default="", description="会话ID")
    role: str = Field(default="", description="消息角色：user / assistant")
    text: str = Field(default="", description="消息原始文本")
    rewritten_query: str = Field(default="", description="改写后的问题")
    # item_names 允许为 None：历史记录可能存的是 None，路由侧 .get(k, []) 在"键存在但值为 None"时返回 None
    item_names: Optional[List[str]] = Field(default=None, description="识别到的商品名列表")
    ts: Optional[float] = Field(default=None, description="记录时间戳（秒）")


class HistoryResponse(BaseModel):
    """查询历史接口响应体（GET /history/{session_id}）"""
    session_id: str = Field(..., description="会话ID")
    items: List[HistoryItem] = Field(default_factory=list, description="历史记录列表（按时间正序）")
