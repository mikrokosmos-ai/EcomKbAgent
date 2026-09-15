"""
节点：知识图谱检索（node_query_kg）

图位置：查询链路的**第 4 条并行召回路**（与 node_search_embedding /
        node_search_embedding_hyde / node_web_search_mcp 并列），下游统一汇入 node_rrf。
作用：把用户问题对齐到图谱中的种子实体 → 一跳扩展拿到关系三元组 →
      组装成 RRF 可融合的 kg_chunks，并把图谱证据交给答案节点单独成区（高信任）。

可用性分级（重要）：
    知识图谱是**可选能力**。本节点整体优雅降级：实体对齐或图查询失败只记 warning，
    返回空 KG 结果，让查询继续走其余三路（不阻断主链路）。

与改造文档 §I-10 的一致性要点：
    · 扩展并行路采用「C-5 方案 A」——只改条件边路由元组与 path_map，不动既有边结构（见 graph.py）；
    · kg_chunks 的 entity 带 type="kg"，由 node_rerank 传播为 reranked_docs 的 type，
      最终被 node_answer_output._split_docs_by_type 分流到图谱证据区（见 §8 C-6）。
"""
import sys
from typing import Any, Dict, List

from app.clients.embedding_client import generate_embeddings
from app.clients.milvus_client import get_milvus_client
from app.conf.milvus_config import milvus_config
from app.conf.query_pipeline_config import query_pipeline_config
from app.core.logger import logger, node_log, step_log
from app.repositories import graph_repo
from app.pipelines.query_pipeline.state import resolve_trace_key
from app.utils.task_utils import add_done_task, add_running_task

ENTITY_COLLECTION_NAME = milvus_config.entity_name_collection
KG_MAX_SEED_CANDIDATES = query_pipeline_config.kg_max_seed_candidates
KG_MAX_TOTAL_TRIPLES = query_pipeline_config.kg_max_total_triples

# 图谱证据在 RRF 融合中的固定"距离"：图谱是确定性结构化知识，其相对排序由 RRF 权重决定
KG_CHUNK_DISTANCE = 1.0


@step_log("step_1_data_validates")
def step_1_data_validates(state):
    """获取并校验入参：确认后的商品名 + 改写后的问题"""
    item_names = state.get("item_names")
    query = state.get("rewritten_query") or state.get("original_query")
    if not item_names or not query:
        raise ValueError("item_names或query不存在,无法继续知识图谱检索")
    return item_names, query


@step_log("step_2_align_seed_entities")
def step_2_align_seed_entities(query: str, item_names: List[str]) -> List[str]:
    """
    实体对齐：把问题向量化，在实体集合中做稠密向量检索，取 top-k 实体名作为种子。

    注意：实体集合只建了稠密向量（无稀疏），因此这里用稠密单路检索，
          不走 create_hybrid_search_requests（那会引用不存在的 sparse_vector 字段）。
    """
    if not ENTITY_COLLECTION_NAME:
        logger.warning("ENTITY_NAME_COLLECTION 未配置，知识图谱检索跳过")
        return []

    milvus_client = get_milvus_client()
    if not milvus_client.has_collection(ENTITY_COLLECTION_NAME):
        logger.warning(f"实体集合 {ENTITY_COLLECTION_NAME} 不存在，知识图谱检索跳过")
        return []

    dense_vector = generate_embeddings([query])["dense"][0]
    hits = milvus_client.search(
        collection_name=ENTITY_COLLECTION_NAME,
        data=[dense_vector],
        anns_field="dense_vector",
        limit=KG_MAX_SEED_CANDIDATES,
        filter=f"item_name in {item_names}",
        output_fields=["entity_name", "label"],
    )

    seeds: List[str] = []
    for hit in (hits[0] if hits else []):
        entity = hit.get("entity", {}) if isinstance(hit, dict) else {}
        name = entity.get("entity_name")
        if name:
            seeds.append(name)
    logger.info(f"实体对齐完成，种子实体：{seeds}")
    return seeds


@step_log("step_3_expand_one_hop")
def step_3_expand_one_hop(seed_names: List[str]) -> List[Dict[str, Any]]:
    """以种子实体为中心做一跳扩展，拿到关系三元组"""
    if not seed_names:
        return []
    triples = graph_repo.fetch_one_hop(seed_names, KG_MAX_TOTAL_TRIPLES)
    logger.info(f"一跳扩展完成，三元组 {len(triples)} 条")
    return triples


@step_log("step_4_build_kg_evidence")
def step_4_build_kg_evidence(triples: List[Dict[str, Any]]):
    """
    把三元组组装成：
        · kg_chunks：RRF 可融合的 {id, distance, entity} 结构
        · description：人类可读的关系描述（日志 / 调试用）
    entity.type 固定为 "kg"，是后续证据分区的唯一依据（§8 C-6）。
    """
    kg_chunks: List[Dict[str, Any]] = []
    lines: List[str] = []
    for triple in triples or []:
        source = triple.get("source")
        relation = triple.get("relation")
        target = triple.get("target")
        if not source or not relation or not target:
            continue
        text = f"{source} —[{relation}]→ {target}"
        kg_id = f"kg::{source}::{relation}::{target}"
        lines.append(text)
        kg_chunks.append({
            "id": kg_id,
            "distance": KG_CHUNK_DISTANCE,
            "entity": {
                "chunk_id": kg_id,
                "title": "知识图谱关系",
                "content": text,
                "type": "kg",  # 关键：供 node_rerank 传播为 type="kg"
            },
        })
    return kg_chunks, "\n".join(lines)


@node_log("node_query_kg")
def node_query_kg(state):
    """
    节点功能：知识图谱检索（第 4 路并行召回）
    入参：item_names / rewritten_query
    出参：{kg_chunks, kg_triples, graph_relation_description}
    步骤：
        1. 日志 + 任务处理
        2. 参数校验
        3. 实体对齐（向量）
        4. 一跳扩展（Neo4j）
        5. 组装 KG 证据
        6. 日志 + 任务处理
    """
    add_running_task(resolve_trace_key(state), sys._getframe().f_code.co_name, state.get("is_stream"))
    kg_chunks: List[Dict[str, Any]] = []
    triples: List[Dict[str, Any]] = []
    description = ""
    try:
        item_names, query = step_1_data_validates(state)
        seeds = step_2_align_seed_entities(query, item_names)
        triples = step_3_expand_one_hop(seeds)
        kg_chunks, description = step_4_build_kg_evidence(triples)
    except Exception as e:
        # 知识图谱是可选能力：失败只告警，让查询继续走其余三路
        logger.warning(f"知识图谱检索失败，已跳过该路召回：{e}", exc_info=True)
        kg_chunks, triples, description = [], [], ""
    add_done_task(resolve_trace_key(state), sys._getframe().f_code.co_name, state.get("is_stream"))
    # 与其它并行分支保持一致：只返回本路产出的字段（由 LangGraph 合并进全局 state）
    return {
        "kg_chunks": kg_chunks,
        "kg_triples": triples,
        "graph_relation_description": description,
    }
