# 导入链路可调参数配置（对应 import_pipeline 各节点）
# 说明：
#   1. 本文件只承载"业务可调参数"，不承载连接信息（连接类配置见 mineru_config / minio_config 等）；
#   2. 每个字段均可用同名环境变量覆盖
#   3. 字段与节点的对应关系写在每个字段的行内注释里，便于反查。
from dataclasses import dataclass
import os
from dotenv import load_dotenv

from app.core.exceptions import ConfigurationError

# 提前加载.env配置文件
load_dotenv()


@dataclass
class ImportPipelineConfig:
    """导入链路可调参数"""

    # ==================== 文档切分（node_document_split）====================
    chunk_max_size: int          # 触发二次切分的长度阈值
    chunk_size: int              # 二次切分时递归切割器的单块长度
    chunk_overlap: int           # 二次切分的块间重叠长度
    chunk_min_size: int          # 最小块长度，低于此值的相邻同源块会被合并

    # ==================== 商品主体识别（node_item_name_recognition）====================
    item_name_chunk_k: int           # 送入 LLM 的上下文切片条数
    item_name_context_max_chars: int  # 上下文总字符上限

    # ==================== 切片向量化（node_bge_embedding）====================
    embedding_batch_size: int    # 每次调用模型的批大小（

    # ==================== 图片摘要限流（node_md_img）====================
    # 说明：VLM 调用有平台侧频率限制，此处为客户端主动节流，避免触发限流导致图片处理失败
    image_summary_rate_max_requests: int      # 窗口内最大请求数
    image_summary_rate_window_seconds: int    # 滑动窗口时长（秒）


# 实例化配置对象，和其他 *_config 命名风格保持一致
import_pipeline_config = ImportPipelineConfig(
    # ---- 文档切分 ----
    chunk_max_size=int(os.getenv("CHUNK_MAX_SIZE", "500")),
    chunk_size=int(os.getenv("CHUNK_SIZE", "200")),
    chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "20")),
    chunk_min_size=int(os.getenv("CHUNK_MIN_SIZE", "100")),
    # ---- 商品主体识别 ----
    item_name_chunk_k=int(os.getenv("ITEM_NAME_CHUNK_K", "5")),
    item_name_context_max_chars=int(os.getenv("ITEM_NAME_CONTEXT_MAX_CHARS", "2500")),
    # ---- 切片向量化 ----
    embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "5")),
    # ---- 图片摘要限流 ----
    image_summary_rate_max_requests=int(os.getenv("IMAGE_SUMMARY_RATE_MAX_REQUESTS", "9")),
    image_summary_rate_window_seconds=int(os.getenv("IMAGE_SUMMARY_RATE_WINDOW_SECONDS", "60")),
)


def _validate_import_pipeline_config(cfg: ImportPipelineConfig) -> None:
    """
    校验导入链路配置的合法性（fail-fast）

    设计意图：
        这些参数之间存在隐含的数学关系（例如 chunk_size 必须不大于触发二次切分的阈值，
        否则"先判断超长、再按更小粒度重切"的两段式切分逻辑就没有意义）。
        若配置矛盾，宁可让服务在启动阶段就明确报错，也不要静默产出错误的切片结果——
        后者会让检索效果悄悄劣化，极难归因。

    注意：默认值天然满足下列全部约束，因此只会拦住"人为改坏"的配置。
    :param cfg: 待校验的导入链路配置
    :raises ConfigurationError: 任意一条不变式被破坏时抛出（错误信息含环境变量名与当前值）
    """
    # 1. 二次切分粒度不能大于触发阈值，否则永远不会按预期粒度切分
    if cfg.chunk_size > cfg.chunk_max_size:
        raise ConfigurationError(
            f"配置冲突：CHUNK_SIZE({cfg.chunk_size}) 不能大于 CHUNK_MAX_SIZE({cfg.chunk_max_size})，"
            f"否则二次切分不会按预期粒度执行"
        )
    # 2. 重叠长度必须小于单块长度，否则递归切割器无法收敛
    if cfg.chunk_overlap >= cfg.chunk_size:
        raise ConfigurationError(
            f"配置冲突：CHUNK_OVERLAP({cfg.chunk_overlap}) 必须小于 CHUNK_SIZE({cfg.chunk_size})，"
            f"否则文本切割器无法正常收敛"
        )
    # 3. 合并阈值不能小于切分粒度，否则「刚切完就被合并」形成死循环式的无谓处理
    if cfg.chunk_min_size > cfg.chunk_max_size:
        raise ConfigurationError(
            f"配置冲突：CHUNK_MIN_SIZE({cfg.chunk_min_size}) 不能大于 CHUNK_MAX_SIZE({cfg.chunk_max_size})"
        )
    # 4. 数值型参数必须为正
    if cfg.chunk_min_size < 0:
        raise ConfigurationError(f"配置非法：CHUNK_MIN_SIZE({cfg.chunk_min_size}) 不能为负数")
    if cfg.item_name_chunk_k <= 0:
        raise ConfigurationError(f"配置非法：ITEM_NAME_CHUNK_K({cfg.item_name_chunk_k}) 必须大于 0")
    if cfg.item_name_context_max_chars <= 0:
        raise ConfigurationError(
            f"配置非法：ITEM_NAME_CONTEXT_MAX_CHARS({cfg.item_name_context_max_chars}) 必须大于 0"
        )
    if cfg.embedding_batch_size <= 0:
        raise ConfigurationError(f"配置非法：EMBEDDING_BATCH_SIZE({cfg.embedding_batch_size}) 必须大于 0")
    if cfg.image_summary_rate_max_requests <= 0 or cfg.image_summary_rate_window_seconds <= 0:
        raise ConfigurationError(
            f"配置非法：IMAGE_SUMMARY_RATE_MAX_REQUESTS({cfg.image_summary_rate_max_requests}) 与 "
            f"IMAGE_SUMMARY_RATE_WINDOW_SECONDS({cfg.image_summary_rate_window_seconds}) 必须大于 0"
        )


# 模块加载即校验：配置矛盾时直接阻断启动，避免带病运行
_validate_import_pipeline_config(import_pipeline_config)
