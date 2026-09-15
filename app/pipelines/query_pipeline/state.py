from typing_extensions import TypedDict
from typing import List
import copy


class QueryGraphState(TypedDict):
    """
    QueryGraphState 定义了整个查询流程中流转的数据结构。
    """
    session_id: str  # 会话唯一标识（Mongo 历史按会话聚合，语义不变）
    task_id: str  # 任务唯一标识：SSE 队列 key + 任务追踪 key
    original_query: str  # 用户原始问题

    # 检索过程中的中间数据
    embedding_chunks: list  # 普通向量检索回来的切片
    hyde_embedding_chunks: list  # HyDE 检索回来的切片
    web_search_docs: list  # 网络搜索回来的文档
    kg_chunks: list  # 知识图谱检索结果（RRF 可融合的 {id, distance, entity} 结构，entity.type="kg"）
    kg_triples: list  # 一跳扩展得到的三元组 [{source, relation, target, item_name}]

    # 排序过程中的数据
    rrf_chunks: list  # RRF 融合排序后的切片
    reranked_docs: list  # 重排序后的最终 Top-K 文档

    # 生成过程中的数据
    prompt: str  # 组装好的 Prompt
    answer: str  # 最终生成的答案

    # 辅助信息
    item_names: List[str]  # 提取出的商品名称
    rewritten_query: str  # 改写后的问题
    history: list  # 历史对话记录
    is_stream: bool  # 是否流式输出标记
    image_urls: List[str]
    graph_relation_description: str  # 图谱关系描述文本（由 node_query_kg 产出，便于日志与调试）


# ========================
# 默认状态（全部为空）
# ========================
query_graph_default_state: QueryGraphState = {
    "session_id": "",
    "task_id": "",
    "original_query": "",
    "embedding_chunks": [],
    "hyde_embedding_chunks": [],
    "web_search_docs": [],
    "kg_chunks": [],
    "kg_triples": [],
    "rrf_chunks": [],
    "reranked_docs": [],
    "prompt": "",
    "answer": "",
    "item_names": [],
    "rewritten_query": "",
    "history": [],
    "is_stream": False,
    "image_urls": [],
    "graph_relation_description": ""
}


# ========================
# 创建默认状态（可覆盖）
# ========================
def create_query_default_state(**overrides) -> QueryGraphState:
    """
    创建查询流程的默认状态，支持覆盖字段
    """
    state = copy.deepcopy(query_graph_default_state)
    state.update(overrides)
    return state


# ========================
# 获取干净状态
# ========================
def get_query_default_state() -> QueryGraphState:
    return copy.deepcopy(query_graph_default_state)


# ========================
# 追踪 key 解析（§I-11 task_id / session_id 分离）
# ========================
def resolve_trace_key(state) -> str:
    """
    解析「任务追踪 / SSE 队列」key。

    I-11 落地后统一使用 task_id（一个会话内可并发多轮查询互不覆盖）；
    为兼容未携带 task_id 的调用方（旧 state、单节点直调、单元测试），
    缺失时回退 session_id —— 等价于改动前的行为，保证零回归。

    注意：Mongo 历史读写（save_chat_message / get_recent_messages）**不走本函数**，
    它们仍应按 session_id 聚合。
    """
    if not isinstance(state, dict):
        return ""
    return state.get("task_id") or state.get("session_id") or ""


# ========================
# ✅ 状态复制函数（你要的）
# ========================
def copy_query_state(state: QueryGraphState, **overrides) -> QueryGraphState:
    """
    复制现有状态并可覆盖字段，深拷贝，不污染原数据
    """
    new_state = copy.deepcopy(state)
    new_state.update(overrides)
    return new_state


if __name__ == "__main__":
    # 测试
    state = create_query_default_state(
        session_id="test_001",
        original_query="华为P60怎么样?",
        is_stream=False
    )
    print("初始化状态：", state)

    # 复制状态
    new_state = copy_query_state(
        state,
        original_query="修改后的问题"
    )
    print("复制后的状态：", new_state)