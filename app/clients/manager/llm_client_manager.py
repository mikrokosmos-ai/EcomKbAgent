"""
LLM 客户端管理器

统一创建和管理 LangChain ChatOpenAI 客户端，支持按 (模型名, JSON 模式) 缓存实例。
"""
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.exceptions import LangChainException

from app.conf.lm_config import lm_config
from app.core.logger import logger


class LLMClientManager:
    def __init__(self, lm_config):
        # 保存 LLM 配置，get() 时按它初始化客户端
        self.lm_config = lm_config
        # 缓存：键为(模型名, JSON输出模式)元组，值为ChatOpenAI实例，避免重复初始化
        self._cache = {}

    def get(self, model: Optional[str] = None, json_mode: bool = False) -> ChatOpenAI:
        # 确定目标模型（优先级递减，保证模型名非空）
        target_model = model or self.lm_config.llm_model or "qwen3-32b"
        cache_key = (target_model, json_mode)

        # 缓存命中：直接返回已初始化的实例
        if cache_key in self._cache:
            logger.debug(f"[LLM客户端] 缓存命中，直接返回实例：模型={target_model}，JSON模式={json_mode}")
            return self._cache[cache_key]

        # 核心配置校验：拦截缺失的API关键配置，提前抛出明确异常
        if not self.lm_config.api_key:
            raise ValueError("[LLM客户端] 配置缺失：请在.env中配置OPENAI_API_KEY（大模型API密钥）")
        if not self.lm_config.base_url:
            raise ValueError("[LLM客户端] 配置缺失：请在.env中配置OPENAI_API_BASE（API接口基础地址）")

        # extra_body：千问等国产模型专属私有参数（LangChain透传至API）
        extra_body = {"enable_thinking": False}
        model_kwargs = {}
        if json_mode:
            model_kwargs["response_format"] = {"type": "json_object"}

        # 客户端初始化：捕获LangChain封装层异常，抛出更友好的提示
        try:
            llm_client = ChatOpenAI(
                model=target_model,
                temperature=self.lm_config.llm_temperature or 0.1,
                api_key=self.lm_config.api_key,
                base_url=self.lm_config.base_url,
                extra_body=extra_body,
                model_kwargs=model_kwargs,
            )
        except LangChainException as e:
            raise Exception(f"[LLM客户端] 模型【{target_model}】初始化失败（LangChain层）：{str(e)}") from e

        # 新实例存入缓存，供后续调用复用
        self._cache[cache_key] = llm_client
        logger.info(f"[LLM客户端] 实例初始化成功并缓存：模型={target_model}，JSON模式={json_mode}")
        return llm_client


# 全局可复用的 LLM 客户端管理器单例
llm_client_manager = LLMClientManager(lm_config)
