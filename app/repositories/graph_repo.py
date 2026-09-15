"""
Neo4j 图数据访问层

只承载「纯 Cypher 执行」：每个函数 = 一组参数化 Cypher，不含业务编排
（对齐 app/repositories/vector_search_repo.py 的职责边界）。

图模型（与 prompts/knowledge_graph.prompt 的抽取结构对齐）：
    (:Chunk {chunk_id, item_name, title})                文档切片锚点
    (:Entity {name, label})                              实体（产品 / 部件 / 操作 / 属性 / 场景 / 其他）
    (:Chunk)-[:MENTIONS]->(:Entity)                      切片提及实体
    (:Entity)-[:REL {relation, item_name}]->(:Entity)    实体间关系

设计说明（与改造文档 §I-10 的一处有意差异，理由是安全）：
    关系名不用 Cypher 的动态 relationship type（动态 type 只能靠字符串拼接，存在注入面），
    统一用单一关系类型 `REL` + `relation` 属性承载关系名；
    "白名单外关系降级 RELATED_TO" 即把 relation 属性置为 RELATED_TO——语义等价、零注入面。
"""
from typing import Any, Dict, List

from app.clients.neo4j_client import get_neo4j_driver
from app.conf.neo4j_config import neo4j_config
from app.core.exceptions import Neo4jError
from app.core.logger import logger

# ==================== Cypher 常量 ====================
# 唯一约束：切片与实体各一条，保证 MERGE 幂等
CYPHER_ENSURE_CONSTRAINTS = (
    "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
)
# 按商品名清理旧图数据：先删该商品的切片锚点，再清理失去所有引用的孤儿实体
CYPHER_DELETE_CHUNKS_BY_ITEM = "MATCH (c:Chunk {item_name: $item_name}) DETACH DELETE c"
CYPHER_DELETE_ORPHAN_ENTITIES = (
    "MATCH (e:Entity) WHERE NOT (e)<-[:MENTIONS]-() AND NOT (e)-[:REL]-() DELETE e"
)
CYPHER_MERGE_CHUNK = (
    "MERGE (c:Chunk {chunk_id: $chunk_id}) "
    "SET c.item_name = $item_name, c.title = $title"
)
CYPHER_MERGE_ENTITIES_BATCH = (
    "UNWIND $rows AS row "
    "MERGE (e:Entity {name: row.name}) "
    "SET e.label = row.label"
)
CYPHER_LINK_ENTITIES_TO_CHUNK = (
    "MATCH (c:Chunk {chunk_id: $chunk_id}) "
    "UNWIND $names AS name "
    "MATCH (e:Entity {name: name}) "
    "MERGE (c)-[:MENTIONS]->(e)"
)
CYPHER_MERGE_RELATIONS_BATCH = (
    "UNWIND $rows AS row "
    "MATCH (a:Entity {name: row.source}) "
    "MATCH (b:Entity {name: row.target}) "
    "MERGE (a)-[r:REL {relation: row.relation, item_name: $item_name}]->(b)"
)
# 查询侧：以种子实体为中心做一跳扩展（双向命中：种子作起点或终点）
CYPHER_FETCH_ONE_HOP = (
    "MATCH (a:Entity)-[r:REL]->(b:Entity) "
    "WHERE a.name IN $names OR b.name IN $names "
    "RETURN DISTINCT a.name AS source, r.relation AS relation, "
    "b.name AS target, r.item_name AS item_name "
    "LIMIT $limit"
)


def _run(cypher: str, **params) -> List[Dict[str, Any]]:
    """
    执行一段 Cypher 并返回记录列表（统一的连接获取与异常归一化）。

    :param cypher: 参数化 Cypher 语句
    :param params: Cypher 参数（一律走参数绑定，不做字符串拼接）
    :return: 记录列表（dict 形式）
    :raises Neo4jError: 连接或执行失败
    """
    try:
        driver = get_neo4j_driver()
        with driver.session(database=neo4j_config.database) as session:
            result = session.run(cypher, **params)
            return [dict(record) for record in result]
    except Exception as e:
        logger.error(f"Neo4j Cypher 执行失败：{e}", exc_info=True)
        raise Neo4jError.wrap(e, node_name="graph_repo") from e


# ==================== 导入侧 ====================
def ensure_schema() -> None:
    """建立唯一约束（幂等，重复调用安全）"""
    for cypher in CYPHER_ENSURE_CONSTRAINTS:
        _run(cypher)


def clear_by_item_name(item_name: str) -> None:
    """按商品名清理旧图数据（切片锚点 + 孤儿实体），保证同一商品的重复导入不残留脏数据"""
    _run(CYPHER_DELETE_CHUNKS_BY_ITEM, item_name=item_name)
    _run(CYPHER_DELETE_ORPHAN_ENTITIES)


def merge_chunk(chunk_id: str, item_name: str, title: str) -> None:
    """写入/更新一个切片锚点节点"""
    _run(CYPHER_MERGE_CHUNK, chunk_id=chunk_id, item_name=item_name or "", title=title or "")


def merge_entities(entities: List[Dict[str, str]]) -> None:
    """
    批量写入实体节点（幂等），并同时落实体类型 label。

    说明：label 是抽取阶段的语义分类（产品 / 部件 / 操作 / 属性 / 场景 / 其他），
    不写进图会导致 Neo4j 侧无法按类型查询/过滤（Milvus 实体集合与 kg.json 都保留了它）。

    :param entities: [{"name": ..., "label": ...}, ...]
                     （对齐 node_import_kg 的 entities 结构；也兼容纯字符串列表，此时 label 记「其他」）
    """
    if not entities:
        return
    rows: List[Dict[str, str]] = []
    seen = set()
    for ent in entities:
        if isinstance(ent, dict):
            name = str(ent.get("name") or "").strip()
            label = str(ent.get("label") or "").strip() or "其他"
        else:
            name = str(ent or "").strip()
            label = "其他"
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append({"name": name, "label": label})
    if not rows:
        return
    _run(CYPHER_MERGE_ENTITIES_BATCH, rows=rows)


def link_entities_to_chunk(chunk_id: str, entity_names: List[str]) -> None:
    """批量建立「切片 -[:MENTIONS]-> 实体」关系"""
    if not entity_names:
        return
    _run(CYPHER_LINK_ENTITIES_TO_CHUNK, chunk_id=chunk_id, names=list(dict.fromkeys(entity_names)))


def merge_relations(rows: List[Dict[str, str]], item_name: str) -> None:
    """批量写入实体间关系；rows = [{source, target, relation}, ...]（幂等）"""
    if not rows:
        return
    _run(CYPHER_MERGE_RELATIONS_BATCH, rows=rows, item_name=item_name or "")


# ==================== 查询侧 ====================
def fetch_one_hop(entity_names: List[str], limit: int) -> List[Dict[str, Any]]:
    """
    以种子实体为中心做一跳扩展，返回关系三元组。

    :param entity_names: 种子实体名列表
    :param limit: 返回条数上限
    :return: [{source, relation, target, item_name}, ...]
    """
    if not entity_names:
        return []
    return _run(CYPHER_FETCH_ONE_HOP, names=list(dict.fromkeys(entity_names)), limit=int(limit))
