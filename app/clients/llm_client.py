"""
LLM 客户端门面

"""
from typing import Optional

from app.clients.manager.llm_client_manager import llm_client_manager


def get_llm_client(model: Optional[str] = None, json_mode: bool = False):
    """
    获取带全局缓存的 ChatOpenAI 客户端实例
    适配 OpenAI/千问/即梦等 OpenAI 兼容 API，支持自定义模型和 JSON 标准化输出
    """
    return llm_client_manager.get(model=model, json_mode=json_mode)
