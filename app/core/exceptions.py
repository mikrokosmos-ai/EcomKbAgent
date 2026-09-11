"""
领域异常体系
作用：
    为「配置 → 客户端 → 导入链路 → 查询链路」提供一套**可辨识的领域异常**，
    让上层（路由 / 后台任务 / 未来的重试与降级逻辑）可以按异常类型做精确处理，
    而不必再去匹配 `str(e)` 的内容。

设计说明：
    1. 统一基类 `AppError`，所有领域异常都携带两个关键上下文：
       - node_name：抛出异常的业务节点名（排查时无需翻调用栈即可定位）
       - cause    ：原始异常对象（保留根因，便于日志打印完整堆栈）
    2. 按链路分三支，避免"一个大而全的异常类"：
       - 配置 / 客户端支：ConfigurationError、ClientInitError
       - 导入链路支    ：FileProcessingError（含 Pdf/Image 细分）、DocumentSplitError、
                        EmbeddingError、StorageError（含 Milvus/Minio/Mongo 细分）
       - 查询链路支    ：SearchError（含 MilvusSearchError）、RerankError、
                        ItemNameConfirmError、StateFieldError、LLMError
    3. 提供 `AppError.wrap()` 统一包装入口，供 `app.core.logger.node_guard` 装饰器复用。

注意事项（重要，请勿"顺手优化"）：
    1. **`app/api/schemas/*` 的 Pydantic 校验器必须继续抛 `ValueError`**，不要改成这里的
       领域异常。原因：Pydantic v2 只把 `ValueError` / `AssertionError` 转换为
       `ValidationError` 并由 FastAPI 返回 422；换成非 ValueError 子类的自定义异常会
       直接穿透校验层，把 422 变成 500，前端的错误处理逻辑会随之失效。
    2. `InputValidationError` 刻意**不继承 `ValueError`**：业务层校验失败与「请求参数格式
       非法」是两类语义不同的问题，混在一起会让 `except ValueError` 意外捕获业务异常。
    3. 命名上刻意避开 `ValidationError`，以免与 `pydantic.ValidationError` 混淆。
    4. 本模块**只能依赖标准库**，保持零依赖，确保它可被依赖图最底层的任何模块安全导入。
"""
from typing import Optional, Type


__all__ = [
    # 基类
    "AppError",
    # 配置 / 客户端
    "ConfigurationError",
    "ClientInitError",
    # 导入链路
    "FileProcessingError",
    "PdfConversionError",
    "ImageProcessingError",
    "DocumentSplitError",
    "EmbeddingError",
    # 查询链路
    "SearchError",
    "MilvusSearchError",
    "RerankError",
    "ItemNameConfirmError",
    "StateFieldError",
    "LLMError",
    # 存储
    "StorageError",
    "MilvusError",
    "MinioError",
    "MongoError",
    "Neo4jError",
    # 通用校验
    "InputValidationError",
]


class AppError(Exception):
    """
    领域异常基类

    所有业务领域异常都继承自此类，统一携带节点名与根因异常，
    让日志输出与上层异常分支判断都能拿到足够的上下文。

    使用示例:
        raise AppError("解析失败", node_name="node_pdf_to_md", cause=e)

        # 或由 node_guard 装饰器自动包装
        wrapped = AppError.wrap(e, node_name="node_pdf_to_md")
    """

    def __init__(
        self,
        message: str,
        node_name: str = "",
        cause: Optional[BaseException] = None,
    ):
        """
        :param message: 面向人的错误描述（中文，说明"哪里错了、期望是什么"）
        :param node_name: 抛出该异常的业务节点名（如 node_document_split），可为空
        :param cause: 原始异常对象，用于保留根因；可为空
        """
        self.message = message
        self.node_name = node_name
        self.cause = cause
        # 交给 Exception 保存原始 message，保证 str(exc) / repr(exc) 行为符合直觉
        super().__init__(message)

    def __str__(self) -> str:
        """
        组装可读的错误信息：`[节点名] 消息 (原因: 根因)`

        设计意图：
            日志里一眼能看到"哪个节点、出了什么事、根因是什么"，
            不必再去翻多层 traceback。
        """
        parts = []
        if self.node_name:
            parts.append(f"[{self.node_name}]")
        parts.append(self.message)
        if self.cause is not None:
            parts.append(f"(原因: {self.cause})")
        return " ".join(parts)

    @classmethod
    def wrap(
        cls,
        exc: BaseException,
        node_name: str = "",
        message: Optional[str] = None,
    ) -> "AppError":
        """
        把任意异常包装为领域异常（幂等）

        :param exc: 待包装的原始异常
        :param node_name: 业务节点名
        :param message: 自定义错误描述；为空时沿用原始异常的字符串表示
        :return: 已是 AppError 则**原样返回**（避免重复包装导致节点名被覆盖），
                 否则返回一个新的 AppError 实例
        """
        # 1. 已归一化过：直接透传，防止 node_guard 嵌套时丢失最初的节点名
        if isinstance(exc, AppError):
            return exc
        # 2. 未归一化：包装为基类异常，并保留 cause 以维持完整堆栈
        return cls(
            message=message or str(exc),
            node_name=node_name,
            cause=exc,
        )


# ============================================================
# 一、配置 / 客户端支
# ============================================================
class ConfigurationError(AppError):
    """
    配置错误：环境变量缺失或取值非法

    典型场景：`MILVUS_URL` 未配置、`OPENAI_API_KEY` 为空、数值型配置无法转 float。
    """
    pass


class ClientInitError(AppError):
    """
    客户端初始化错误：外部依赖（Milvus / Mongo / MinIO / 本地模型）建连或加载失败

    典型场景：Milvus 端口不通、BGE-M3 权重文件缺失。
    """
    pass


# ============================================================
# 二、导入链路支
# ============================================================
class FileProcessingError(AppError):
    """文件处理错误：文件不存在、路径非法、读写失败"""
    pass


class PdfConversionError(FileProcessingError):
    """PDF 转换错误：MinerU 提交/轮询/解压失败，或解析超时"""
    pass


class ImageProcessingError(FileProcessingError):
    """图片处理错误：图片上下文抽取、VLM 摘要、上传 MinIO 或路径替换失败"""
    pass


class DocumentSplitError(AppError):
    """文档切分错误：`md_content` 为空、切分结果为空等"""
    pass


class EmbeddingError(AppError):
    """向量化错误：BGE-M3 调用失败、dense/sparse 格式异常或长度不匹配"""
    pass


# ============================================================
# 三、查询链路支
# ============================================================
class SearchError(AppError):
    """检索错误：向量检索、HyDE 检索或联网搜索失败"""
    pass


class MilvusSearchError(SearchError):
    """Milvus 检索错误：混合检索返回 None、命中结果结构不符合预期"""
    pass


class RerankError(AppError):
    """重排错误：Cross-Encoder 打分失败或分数与文档数量不一致"""
    pass


class ItemNameConfirmError(AppError):
    """商品名识别 / 确认错误：LLM 输出无法解析、向量库无匹配且无兜底分支"""
    pass


class LLMError(AppError):
    """LLM 调用错误：API 调用失败、响应为空或 JSON 解析失败"""
    pass


class StateFieldError(AppError):
    """
    状态字段错误：从 state 中取必需字段时缺失、为空或类型不符

    相比裸 `ValueError("xx 不能为空")`，本异常把**字段名**与**期望类型**结构化，
    便于上层做统一的错误提示以及未来的入参 Schema 化。

    使用示例:
        raise StateFieldError(
            field_name="original_query",
            expected_type=str,
            node_name="node_item_name_confirm",
        )
    """

    def __init__(
        self,
        field_name: str,
        expected_type: Optional[Type] = None,
        node_name: str = "",
        message: str = "",
        cause: Optional[BaseException] = None,
    ):
        """
        :param field_name: 缺失或非法的状态字段名
        :param expected_type: 期望的字段类型（可选，用于生成更具体的提示）
        :param node_name: 业务节点名
        :param message: 自定义描述；为空时按 field_name / expected_type 自动生成
        :param cause: 原始异常对象
        """
        self.field_name = field_name
        self.expected_type = expected_type
        # 未显式给 message 时，按字段名 + 期望类型自动拼装，减少调用方的重复文案
        if not message:
            message = f"状态字段 '{field_name}' 缺失或非法"
            if expected_type is not None:
                message += f"，期望类型: {getattr(expected_type, '__name__', expected_type)}"
        super().__init__(message=message, node_name=node_name, cause=cause)


# ============================================================
# 四、存储支（导入 / 查询双向共用）
# ============================================================
class StorageError(AppError):
    """存储错误：数据库 / 对象存储操作失败"""
    pass


class MilvusError(StorageError):
    """Milvus 存储错误：建集合、插入、删除或 load 失败"""
    pass


class MinioError(StorageError):
    """MinIO 存储错误：建桶、上传或设置桶策略失败"""
    pass


class MongoError(StorageError):
    """MongoDB 存储错误：会话历史读写失败"""
    pass


class Neo4jError(StorageError):
    """
    图数据库存储错误：Neo4j 连接、Cypher 执行或图数据读写失败

    说明：当前版本尚未接入知识图谱链路，本异常类为**预留项**，
    供后续「知识图谱导入 / 查询」节点直接使用，以保持存储支的完整性
    （Milvus / MinIO / Mongo / Neo4j 四类存储各有一个对应异常）。
    """
    pass


# ============================================================
# 五、通用校验支
# ============================================================
class InputValidationError(AppError):
    """
    业务入参校验错误（非 HTTP 层参数校验）

    适用范围：经过 FastAPI 参数绑定之后，进入业务逻辑时才发现的数据问题，
    例如"state 里的 chunks 为空"、"item_names 与向量检索结果数量不匹配"。

    注意：**HTTP 请求体本身的格式校验请继续使用 Pydantic 的 `ValueError`**，
    否则会把本该返回 422 的请求变成 500（详见模块头「注意事项」第 1 条）。
    """
    pass
