import sys
from app.conf.milvus_config import milvus_config
from app.clients.embedding_client import generate_embeddings
from app.clients.milvus_client import get_milvus_client
from app.repositories.vector_search_repo import create_hybrid_search_requests, hybrid_search
from app.core.logger import logger, node_log, step_log
from dotenv import load_dotenv, find_dotenv
from app.utils.task_utils import add_done_task, add_running_task
from app.conf.query_pipeline_config import query_pipeline_config

# load_dotenv 加载 .env 文件  find_dotenv() .env文件在项目下的任何位置都可以加载!
load_dotenv(find_dotenv())

# 切片混合检索参数（来源：app/conf/query_pipeline_config.py，默认值等于改造前的字面量现值）
# 稠密/稀疏向量权重
CHUNK_SEARCH_WEIGHTS = (
    query_pipeline_config.chunk_search_dense_weight,
    query_pipeline_config.chunk_search_sparse_weight,
)
# 单路检索返回条数
CHUNK_SEARCH_LIMIT = query_pipeline_config.chunk_search_limit


@step_log("step_1_data_validates")
def step_1_data_validates(state):
    """
    获取参数并且校验
    :param state:
    :return:
    """
    item_names = state.get("item_names")
    rewritten_query = state.get("rewritten_query")
    if not item_names or not rewritten_query:
        logger.error("item_names或rewritten_query不存在,无法继续业务!")
        raise ValueError("item_names或rewritten_query不存在,无法继续业务!")
    return item_names, rewritten_query


@step_log("step_2_rewritten_query_vector")
def step_2_rewritten_query_vector(rewritten_query):
    result = generate_embeddings([rewritten_query])
    return result['dense'][0], result['sparse'][0]


@step_log("step_3_mivlus_hybrid_search")
def step_3_mivlus_hybrid_search(dense_vector, sparse_vector, item_names):
    """
    向量搜索
        混合搜索 +  过滤条件  item_name in [a,b,c] mivlus ->mysql ()
    混合搜索步骤:
        1. 创建对应AnnSearchRequest
        2. 定义对应reranker
        3. 调用混合检索方法就行
    :param dense_vector:
    :param sparse_vector:
    :param item_names:
    :return:
    """
    # 1. 获取mivlus客户端
    mivlus_client = get_milvus_client()
    # 2. 封装请求对象列表
    expr_str = f"item_name in {item_names}"  # item_name in ['a','b','c','d']
    reqs = create_hybrid_search_requests(dense_vector, sparse_vector, expr=expr_str)
    # 3. 混合检索
    resp = hybrid_search(
        client=mivlus_client,
        collection_name=milvus_config.chunks_collection,
        reqs=reqs,
        ranker_weights=CHUNK_SEARCH_WEIGHTS,  # 稠密/稀疏权重（配置项，默认 0.8 / 0.2）
        norm_score=True,
        limit=CHUNK_SEARCH_LIMIT,
        output_fields=["chunk_id", "file_title","item_name", "content", "title", "parent_title", "part" ]
    )
    return resp[0] if resp and len(resp) > 0 else []


@node_log("node_search_embedding")
def node_search_embedding(state):
    """
    节点功能：进行向量内容检索
    """
    # 1. 日志和任务处理
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))
    # 2. 参数获取和校验(item_names / rewritten_query)
    item_names, rewritten_query = step_1_data_validates(state)
    # 3. 问题向量化获取稠密和稀疏向量
    dense_vector, sparse_vector = step_2_rewritten_query_vector(rewritten_query)
    # 4. 进行混合检索(过滤条件/双向量和权重设置/输出字段控制)
    mivlus_result = step_3_mivlus_hybrid_search(dense_vector, sparse_vector, item_names)
    # 5. 返回结果即可
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))
    return {"embedding_chunks": mivlus_result}


if __name__ == "__main__":
    # 模拟测试数据
    test_state = {
        "session_id": "test_search_embedding_001",
        "rewritten_query": "HAK 180 烫金机# 对于本设备所有者不遵守本指南中规定的说明操作而导致的损害，Brother 不承担任何责任。",
        # 模拟改写后的查询
        "item_names": ["HAK 180 烫金机"],  # 模拟已确认的商品名
        "is_stream": False
    }

    print("\n>>> 开始测试 node_search_embedding 节点...")
    try:
        # 执行节点函数
        result = node_search_embedding(test_state)
        logger.info(f"检索结果汇总：{result}")
        # 验证结果
        chunks = result.get("embedding_chunks", [])
        print(f"\n>>> 测试完成！检索到 {len(chunks)} 条结果")
        print(f"\n>>> 测试完成！检索到 {chunks} 条结果")
    except Exception as e:
        logger.error(f"测试运行失败: {e}", exc_info=True)