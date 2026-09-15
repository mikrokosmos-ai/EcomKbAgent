"""
节点：知识图谱抽取与入库（node_import_kg）

图位置：导入链路末端，前驱 node_import_milvus —— **线性尾插**，
        不改变任何既有节点的入度 / 出度契约。
作用：把本次导入的切片交给 LLM 抽取「实体 + 关系」，清洗过滤后
      实体名向量写入 Milvus 的实体集合、三元组写入 Neo4j，并落 kg.json 备份。

可用性分级（重要）：
    知识图谱是**可选能力**——与 lifespan 对 neo4j 的分级一致，本节点整体做了
    优雅降级：抽取 / 入库失败只记 warning，不抛错、不阻断导入主链路
    （否则 Neo4j 未启动会让每一次文档导入都失败）。

设计差异（与改造文档 §I-10 的一处有意偏离，理由是安全）：
    关系名以属性形式存放在单一关系类型 REL 上（详见 app/repositories/graph_repo.py 顶部说明）。
"""
import json
import os
import sys
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pymilvus import DataType

from app.clients.embedding_client import generate_embeddings
from app.clients.llm_client import get_llm_client
from app.clients.milvus_client import get_milvus_client
from app.conf.import_pipeline_config import (
    KG_ALLOWED_ENTITY_LABELS,
    KG_ALLOWED_RELATION_TYPES,
    KG_RELATION_FALLBACK,
    import_pipeline_config,
)
from app.conf.milvus_config import milvus_config
from app.core.logger import logger, node_log, step_log
from app.pipelines.import_pipeline.state import ImportGraphState
from app.prompts.loader import load_prompt
from app.repositories import graph_repo
from app.utils.escape_milvus_string_utils import escape_milvus_string
from app.utils.task_utils import add_done_task, add_running_task

# 实体集合名（Milvus），与切片集合 kd_db_chunks 并列
ENTITY_COLLECTION_NAME = milvus_config.entity_name_collection
# 实体名长度上限（超出即截断，避免把整句话当实体）
ENTITY_NAME_MAX_LENGTH = import_pipeline_config.entity_name_max_length
# 稠密向量维度：与 node_import_milvus 建库维度保持一致（BGE-M3 原生 1024）
DENSE_DIM = 1024

SYSTEM_PROMPT = "你是电商知识库的知识图谱抽取器，只输出 JSON，不输出任何解释。"


# ==================== 步骤实现 ====================
@step_log("step_1_validate_chunks")
def step_1_validate_chunks(state) -> List[Dict[str, Any]]:
    """参数校验：chunks 为空属正常场景，**不抛错**，返回空列表让调用方跳过"""
    chunks = state.get("chunks") or []
    if not chunks:
        logger.warning("chunks 为空，知识图谱抽取跳过")
    return chunks


@step_log("step_2_clear_old_data")
def step_2_clear_old_data(state) -> None:
    """按 item_name 清理旧图数据（Neo4j 切片锚点/孤儿实体 + Milvus 实体向量），保证重复导入不残留"""
    item_name = state.get("item_name") or ""
    if not item_name:
        logger.warning("item_name 为空，跳过旧知识图谱数据清理")
        return
    # 1. Neo4j
    graph_repo.clear_by_item_name(item_name)
    # 2. Milvus 实体集合（存在才清理）
    if ENTITY_COLLECTION_NAME:
        milvus_client = get_milvus_client()
        if milvus_client.has_collection(ENTITY_COLLECTION_NAME):
            milvus_client.delete(
                collection_name=ENTITY_COLLECTION_NAME,
                filter=f'item_name=="{escape_milvus_string(item_name)}"',
            )
            milvus_client.load_collection(collection_name=ENTITY_COLLECTION_NAME)


@step_log("step_3_llm_extract")
def step_3_llm_extract(item_name: str, chunk_text: str) -> Dict[str, Any]:
    """对单个切片做一次结构化抽取，返回 {entities, relations}（异常由调用方兜底）"""
    llm_client = get_llm_client(json_mode=True)
    prompt = load_prompt(
        "knowledge_graph",
        item_name=item_name or "未识别商品",
        chunk_text=chunk_text or "",
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
    chain = llm_client | JsonOutputParser()
    result = chain.invoke(messages)
    if not isinstance(result, dict):
        logger.warning("知识图谱抽取返回非 dict，按空结果处理")
        return {"entities": [], "relations": []}
    return {
        "entities": result.get("entities") or [],
        "relations": result.get("relations") or [],
    }


def _extract_all(chunks: List[Dict[str, Any]], item_name: str) -> List[Tuple[Dict, Dict]]:
    """逐切片顺序抽取（顺序执行以避免触发平台限流；单切片失败只跳过该切片）"""
    per_chunk: List[Tuple[Dict, Dict]] = []
    for chunk in chunks:
        text = (chunk.get("content") or "").strip()
        if not text:
            continue
        try:
            per_chunk.append((chunk, step_3_llm_extract(item_name, text)))
        except Exception as e:
            logger.warning(f"切片 {chunk.get('chunk_id')} 知识图谱抽取失败，跳过：{e}")
    return per_chunk


def _normalize_name(raw) -> str:
    """
    归一化实体名：去首尾空白 → 按上限截断 → **再次去尾空白**。

    第二次 strip 是必要的：截断点可能恰好落在空格上（例如
    "AC 220 V-240 V 电脑" 截到 15 位会得到 "AC 220 V-240 V "），
    尾空格会污染图谱、破坏实体名的精确匹配，必须清掉。
    """
    return str(raw or "").strip()[:ENTITY_NAME_MAX_LENGTH].strip()


@step_log("step_4_clean_and_filter")
def step_4_clean_and_filter(per_chunk: List[Tuple[Dict, Dict]]):
    """
    清洗与过滤（对应 §I-10 step_4）：
        1. 实体名去空白 + 截断到上限；label 不在白名单内降级为「其他」
        2. 关系 head/tail 必须落在实体集合内，否则丢弃（防幻觉悬空边）
        3. 关系类型不在白名单内降级为 RELATED_TO
        4. 实体 / 关系全部去重

    :return: (entities, relations, chunk_entity_names)
             entities = [{name, label}, ...]
             relations = [{head, relation, tail}, ...]
             chunk_entity_names = {chunk_id: [实体名, ...]}（用于建 MENTIONS 边）
    """
    entity_map: Dict[str, str] = {}
    chunk_entity_names: Dict[str, set] = {}

    # 第一遍：归一化实体
    for chunk, res in per_chunk:
        names_here = set()
        for ent in res.get("entities") or []:
            if not isinstance(ent, dict):
                continue
            name = _normalize_name(ent.get("name"))
            if not name:
                continue
            label = str(ent.get("label") or "").strip()
            if label not in KG_ALLOWED_ENTITY_LABELS:
                label = "其他"
            entity_map.setdefault(name, label)   # 同名实体保留首次出现的 label
            names_here.add(name)
        chunk_entity_names.setdefault(str(chunk.get("chunk_id")), set()).update(names_here)

    known = set(entity_map.keys())

    # 第二遍：过滤关系
    relations: List[Dict[str, str]] = []
    seen = set()
    for _, res in per_chunk:
        for rel in res.get("relations") or []:
            if not isinstance(rel, dict):
                continue
            head = _normalize_name(rel.get("head"))
            tail = _normalize_name(rel.get("tail"))
            if not head or not tail or head == tail:
                continue
            if head not in known or tail not in known:
                logger.debug(f"丢弃关系（head/tail 未在实体集合中）：{head} -{rel.get('relation')}-> {tail}")
                continue
            relation = str(rel.get("relation") or "").strip()
            if relation not in KG_ALLOWED_RELATION_TYPES:
                relation = KG_RELATION_FALLBACK
            key = (head, relation, tail)
            if key in seen:
                continue
            seen.add(key)
            relations.append({"head": head, "relation": relation, "tail": tail})

    entities = [{"name": name, "label": label} for name, label in entity_map.items()]
    logger.info(f"知识图谱清洗完成：实体 {len(entities)} 个，关系 {len(relations)} 条")
    return entities, relations, chunk_entity_names


@step_log("step_5_insert_entity_milvus")
def step_5_insert_entity_milvus(entities: List[Dict[str, str]], item_name: str) -> None:
    """实体名向量化后写入 Milvus 实体集合（集合不存在则按与切片集合同构的 schema 创建）"""
    if not entities:
        return
    if not ENTITY_COLLECTION_NAME:
        logger.warning("ENTITY_NAME_COLLECTION 未配置，跳过实体向量入库")
        return

    milvus_client = get_milvus_client()
    # 1. 准备集合
    if not milvus_client.has_collection(ENTITY_COLLECTION_NAME):
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="entity_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="entity_name", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="label", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=DENSE_DIM)

        index_params = milvus_client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="AUTOINDEX",
            metric_type="IP",  # 与切片集合一致：BGE-M3 已 L2 归一化，IP ≡ COSINE
        )
        milvus_client.create_collection(
            collection_name=ENTITY_COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )

    # 2. 向量化（只要稠密向量；稀疏向量与本集合无关）
    names = [e["name"] for e in entities]
    embeddings = generate_embeddings(names)
    rows = [
        {
            "entity_name": ent["name"],
            "item_name": item_name or "",
            "label": ent["label"],
            "dense_vector": embeddings["dense"][i],
        }
        for i, ent in enumerate(entities)
    ]
    # 3. 写入并加载
    milvus_client.insert(collection_name=ENTITY_COLLECTION_NAME, data=rows)
    milvus_client.load_collection(collection_name=ENTITY_COLLECTION_NAME)
    logger.info(f"实体向量入库完成：{len(rows)} 条 → {ENTITY_COLLECTION_NAME}")


@step_log("step_6_insert_neo4j")
def step_6_insert_neo4j(chunks, entities, relations, chunk_entity_names, item_name) -> None:
    """写入 Neo4j：实体 → 切片锚点与 MENTIONS → 实体间关系（顺序保证 MATCH 命中）"""
    graph_repo.ensure_schema()

    # 1. 实体必须先落库（带 label），后续 MENTIONS / REL 的 MATCH 才能命中
    graph_repo.merge_entities(entities)

    # 2. 切片锚点 + 切片提及的实体
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if chunk_id is None:
            continue
        graph_repo.merge_chunk(str(chunk_id), item_name or "", chunk.get("title") or "")
        hit_names = list(chunk_entity_names.get(str(chunk_id), set()))
        graph_repo.link_entities_to_chunk(str(chunk_id), hit_names)

    # 3. 实体间关系
    graph_repo.merge_relations(
        [{"source": r["head"], "target": r["tail"], "relation": r["relation"]} for r in relations],
        item_name or "",
    )
    logger.info(f"知识图谱入库完成：实体 {len(entities)} 个，关系 {len(relations)} 条 → Neo4j")


@step_log("step_7_backup_data")
def step_7_backup_data(state, entities, relations) -> None:
    """把本次抽取结果落 kg.json，便于人工核对与回溯（对齐既有中间产物实践）"""
    local_dir = state.get("local_dir") or ""
    if not local_dir:
        return
    try:
        os.makedirs(local_dir, exist_ok=True)
        backup_path = os.path.join(local_dir, "kg.json")
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "item_name": state.get("item_name") or "",
                    "entities": entities,
                    "relations": relations,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        logger.info(f"知识图谱备份已写入：{backup_path}")
    except Exception as e:
        logger.warning(f"知识图谱备份写入失败：{e}")


@node_log("node_import_kg")
def node_import_kg(state: ImportGraphState) -> ImportGraphState:
    """
    节点: 知识图谱抽取与入库 (node_import_kg)
    入参: chunks / item_name / local_dir
    出参: state['kg_result'] = {"entities": N, "relations": M}
    步骤:
        1. 日志 + 任务处理
        2. 参数校验（chunks 为空则跳过，不抛错）
        3. 清理该 item_name 的旧图谱数据
        4. LLM 逐切片抽取
        5. 清洗过滤（截断 / 白名单 / 降级 / 去重）
        6. 实体向量入 Milvus
        7. 三元组入 Neo4j
        8. kg.json 备份
        9. 日志 + 任务处理
    """
    add_running_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    chunks = step_1_validate_chunks(state)

    if not chunks:
        state["kg_result"] = {"entities": 0, "relations": 0, "skipped": True}
        add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
        return state

    item_name = state.get("item_name") or ""
    try:
        # 1. 清理旧数据
        step_2_clear_old_data(state)
        # 2. LLM 逐切片抽取
        per_chunk = _extract_all(chunks, item_name)
        # 3. 清洗过滤
        entities, relations, chunk_entity_names = step_4_clean_and_filter(per_chunk)
        # 4. 入库（无实体时跳过写库，但仍落备份）
        if entities:
            step_5_insert_entity_milvus(entities, item_name)
            step_6_insert_neo4j(chunks, entities, relations, chunk_entity_names, item_name)
        # 5. 备份
        step_7_backup_data(state, entities, relations)
        state["kg_result"] = {"entities": len(entities), "relations": len(relations)}
    except Exception as e:
        # 知识图谱是可选能力：失败只告警，不阻断导入主链路（与 lifespan 对 neo4j 的分级一致）
        logger.warning(
            f"[{state.get('task_id')}] 知识图谱导入失败，已跳过（不影响切片向量入库）：{e}",
            exc_info=True,
        )
        state["kg_result"] = {"entities": 0, "relations": 0, "error": str(e)}

    add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    return state
