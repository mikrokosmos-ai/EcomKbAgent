# 查询链路可调参数配置（对应 query_pipeline 各节点）
# 说明：
#   1. 本文件只承载"业务可调参数"，不承载连接信息（连接类配置见 milvus_config / lm_config 等）；
#   2. 每个字段均可用同名环境变量覆盖，
#   3. 字段与节点的对应关系写在每个字段的行内注释里，便于反查；
#   4. 历史对话预算（HISTORY_BUDGET）不在此声明：它是
#      「总预算 - 本地证据 - 联网证据」推导出来的，派生而非独立配置，
#      这样可从构造上保证"三段之和不超总预算"这一不变式。
from dataclasses import dataclass
import os
from dotenv import load_dotenv

from app.core.exceptions import ConfigurationError

# 提前加载.env配置文件（保持和原代码一致，只需执行一次）
load_dotenv()


@dataclass
class QueryPipelineConfig:
    """查询链路可调参数"""

    # ==================== 重排与动态截断（node_rerank）====================
    rerank_max_topk: int         # 动态 TopK 硬上限
    rerank_min_topk: int         # 动态 TopK 下限，至少保留的条数
    rerank_gap_ratio: float      # 断崖检测：相对落差阈值
    rerank_gap_abs: float        # 断崖检测：绝对分差阈值

    # ==================== 多路融合（node_rrf）====================
    rrf_k: int                   # RRF 平滑参数，削弱排名影响
    rrf_top: int                 # 融合后保留条数

    # ==================== 商品名确认（node_item_name_confirm）====================
    item_name_high_threshold: float      # 高置信阈值，达到即确认
    item_name_mid_threshold: float       # 中置信下限，介于两者之间转"待用户确认"
    item_name_max_options: int           # 待确认时最多给出的候选数量
    item_name_match_dense_weight: float   # 商品名向量匹配：稠密向量权重
    item_name_match_sparse_weight: float  # 商品名向量匹配：稀疏向量权重

    # ==================== 切片检索（node_search_embedding / node_search_embedding_hyde）====================
    chunk_search_dense_weight: float    # 切片混合检索：稠密向量权重
    chunk_search_sparse_weight: float   # 切片混合检索：稀疏向量权重
    chunk_search_limit: int             # 单路检索返回条数

    # ==================== 答案生成（node_answer_output）====================
    max_context_chars: int       # 上下文总字符预算
    local_evidence_budget: int   # 本地知识库证据区预算
    web_evidence_budget: int     # 联网证据区预算

    # ==================== 联网搜索（node_web_search_mcp）====================
    web_search_count: int        # MCP 联网搜索返回条数


# 实例化配置对象，和其他 *_config 命名风格保持一致
query_pipeline_config = QueryPipelineConfig(
    # ---- 重排与动态截断 ----
    rerank_max_topk=int(os.getenv("RERANK_MAX_TOPK", "10")),
    rerank_min_topk=int(os.getenv("RERANK_MIN_TOPK", "1")),
    rerank_gap_ratio=float(os.getenv("RERANK_GAP_RATIO", "0.25")),
    rerank_gap_abs=float(os.getenv("RERANK_GAP_ABS", "0.5")),
    # ---- 多路融合 ----
    rrf_k=int(os.getenv("RRF_K", "60")),
    rrf_top=int(os.getenv("RRF_TOP", "5")),
    # ---- 商品名确认 ----
    item_name_high_threshold=float(os.getenv("ITEM_NAME_HIGH_THRESHOLD", "0.65")),
    item_name_mid_threshold=float(os.getenv("ITEM_NAME_MID_THRESHOLD", "0.50")),
    item_name_max_options=int(os.getenv("ITEM_NAME_MAX_OPTIONS", "2")),
    item_name_match_dense_weight=float(os.getenv("ITEM_NAME_MATCH_DENSE_WEIGHT", "0.5")),
    item_name_match_sparse_weight=float(os.getenv("ITEM_NAME_MATCH_SPARSE_WEIGHT", "0.5")),
    # ---- 切片检索 ----
    chunk_search_dense_weight=float(os.getenv("CHUNK_SEARCH_DENSE_WEIGHT", "0.8")),
    chunk_search_sparse_weight=float(os.getenv("CHUNK_SEARCH_SPARSE_WEIGHT", "0.2")),
    chunk_search_limit=int(os.getenv("CHUNK_SEARCH_LIMIT", "5")),
    # ---- 答案生成 ----
    max_context_chars=int(os.getenv("MAX_CONTEXT_CHARS", "12000")),
    local_evidence_budget=int(os.getenv("LOCAL_EVIDENCE_BUDGET", "8000")),
    web_evidence_budget=int(os.getenv("WEB_EVIDENCE_BUDGET", "2500")),
    # ---- 联网搜索 ----
    web_search_count=int(os.getenv("WEB_SEARCH_COUNT", "10")),
)


def _validate_query_pipeline_config(cfg: QueryPipelineConfig) -> None:
    """
    校验查询链路配置的合法性（fail-fast）

    设计意图：
        与导入链路同理——参数之间存在隐含约束（如 TopK 上下限必须有序、
        证据区预算之和不能超过总预算），配置矛盾时应在启动阶段明确报错，
        而不是让检索结果静默劣化。

    注意：默认值天然满足下列全部约束，因此只会拦住"人为改坏"的配置。
    :param cfg: 待校验的查询链路配置
    :raises ConfigurationError: 任意一条不变式被破坏时抛出（错误信息含环境变量名与当前值）
    """
    # 1. TopK 上下限必须有序，且下限至少为 1（保证无论如何都保留结果）
    if cfg.rerank_min_topk < 1:
        raise ConfigurationError(f"配置非法：RERANK_MIN_TOPK({cfg.rerank_min_topk}) 必须大于等于 1")
    if cfg.rerank_min_topk > cfg.rerank_max_topk:
        raise ConfigurationError(
            f"配置冲突：RERANK_MIN_TOPK({cfg.rerank_min_topk}) 不能大于 "
            f"RERANK_MAX_TOPK({cfg.rerank_max_topk})"
        )
    # 2. 断崖阈值必须为非负
    if cfg.rerank_gap_ratio < 0 or cfg.rerank_gap_abs < 0:
        raise ConfigurationError(
            f"配置非法：RERANK_GAP_RATIO({cfg.rerank_gap_ratio}) 与 RERANK_GAP_ABS({cfg.rerank_gap_abs}) "
            f"不能为负数"
        )
    # 3. 证据区预算之和不能超过总预算，否则历史对话预算会变成负数而被静默截断
    evidence_sum = cfg.local_evidence_budget + cfg.web_evidence_budget
    if evidence_sum > cfg.max_context_chars:
        raise ConfigurationError(
            f"配置冲突：LOCAL_EVIDENCE_BUDGET({cfg.local_evidence_budget}) + "
            f"WEB_EVIDENCE_BUDGET({cfg.web_evidence_budget}) = {evidence_sum} "
            f"不能大于 MAX_CONTEXT_CHARS({cfg.max_context_chars})，"
            f"否则历史对话区预算将为负数"
        )
    # 4. 商品名置信度区间必须有序且在 [0, 1] 内，否则确认/待确认分支永远不会命中
    if not 0.0 <= cfg.item_name_mid_threshold <= cfg.item_name_high_threshold <= 1.0:
        raise ConfigurationError(
            f"配置冲突：需满足 0 <= ITEM_NAME_MID_THRESHOLD({cfg.item_name_mid_threshold}) <= "
            f"ITEM_NAME_HIGH_THRESHOLD({cfg.item_name_high_threshold}) <= 1"
        )
    # 5. 条数类参数必须为正
    if cfg.rrf_top <= 0:
        raise ConfigurationError(f"配置非法：RRF_TOP({cfg.rrf_top}) 必须大于 0")
    if cfg.item_name_max_options <= 0:
        raise ConfigurationError(f"配置非法：ITEM_NAME_MAX_OPTIONS({cfg.item_name_max_options}) 必须大于 0")
    if cfg.chunk_search_limit <= 0:
        raise ConfigurationError(f"配置非法：CHUNK_SEARCH_LIMIT({cfg.chunk_search_limit}) 必须大于 0")
    if cfg.web_search_count <= 0:
        raise ConfigurationError(f"配置非法：WEB_SEARCH_COUNT({cfg.web_search_count}) 必须大于 0")
    # 6. 检索权重必须为非负（Milvus WeightedRanker 不接受负权重）
    for name, value in (
        ("ITEM_NAME_MATCH_DENSE_WEIGHT", cfg.item_name_match_dense_weight),
        ("ITEM_NAME_MATCH_SPARSE_WEIGHT", cfg.item_name_match_sparse_weight),
        ("CHUNK_SEARCH_DENSE_WEIGHT", cfg.chunk_search_dense_weight),
        ("CHUNK_SEARCH_SPARSE_WEIGHT", cfg.chunk_search_sparse_weight),
    ):
        if value < 0:
            raise ConfigurationError(f"配置非法：{name}({value}) 不能为负数")


# 模块加载即校验：配置矛盾时直接阻断启动，避免带病运行
_validate_query_pipeline_config(query_pipeline_config)
