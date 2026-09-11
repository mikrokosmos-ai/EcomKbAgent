# HyDE节点
import sys

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

from app.utils.task_utils import add_running_task, add_done_task
from app.clients.llm_client import get_llm_client
from app.clients.embedding_client import generate_embeddings
from app.clients.milvus_client import get_milvus_client
from app.repositories.vector_search_repo import create_hybrid_search_requests, hybrid_search
from app.conf.milvus_config import milvus_config
from app.core.logger import logger, node_log, step_log
from app.prompts.loader import load_prompt
from app.conf.query_pipeline_config import query_pipeline_config
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# 切片混合检索参数（来源：app/conf/query_pipeline_config.py，默认值等于改造前的字面量现值）
# 说明：与 node_search_embedding 共用同一组配置，保证两路召回参数一致
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


@step_log("step_2_call_llm")
def step_2_call_llm(rewritten_query):
    """
    调用llm模型,给与普通字符回答!
    :param rewritten_query:
    :return:
    """
    # 1.获取lm客户端对象
    lm_client = get_llm_client()
    # 2.准备提示词 组装Message
    prompt_str = load_prompt("hyde_prompt", rewritten_query=rewritten_query)
    messages = [
        HumanMessage(content=prompt_str)
    ]
    # 3.组装chains
    lm_chains = lm_client | StrOutputParser()
    # 4.执行获取结果
    hyde_answer = lm_chains.invoke(messages)
    # 5.返回结果
    return hyde_answer


@step_log("step_3_rewritten_hyde_vector")
def step_3_rewritten_hyde_vector(rewritten_query, hyde_answer):
    # 拼接完整字符
    vector_str = rewritten_query + "," + hyde_answer
    result = generate_embeddings([vector_str])
    return result['dense'][0], result['sparse'][0]


@step_log("step_4_mivlus_hybrid_search")
def step_4_mivlus_hybrid_search(dense_vector, sparse_vector, item_names):
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
        output_fields=["chunk_id", "item_name", "content", "title", "parent_title", "part", "file_title"]
    )
    return resp[0] if resp and len(resp) > 0 else []


@node_log("node_search_embedding_hyde")
def node_search_embedding_hyde(state):
    """
    节点功能：HyDE (Hypothetical Document Embedding)
    先让 LLM 生成假设性答案，再对答案进行向量检索，提高召回率。
    """
    # 1. 日志和任务处理
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))
    # 2. 参数获取和校验(item_names / rewritten_query)
    item_names, rewritten_query = step_1_data_validates(state)
    # 3. 根据重写的问题调用模型查询答案
    hyde_answer = step_2_call_llm(rewritten_query)
    # 4. 进行问题+答案拼接,并且生成对应的向量
    dense_vector, sparse_vector = step_3_rewritten_hyde_vector(rewritten_query, hyde_answer)
    # 5. 进行混合检索(过滤条件/双向量和权重设置/输出字段控制)
    mivlus_result = step_4_mivlus_hybrid_search(dense_vector, sparse_vector, item_names)
    # 6. 返回结果即可
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))
    return {"hyde_embedding_chunks": mivlus_result}



if __name__ == "__main__":
    # 本地测试代码
    print("\n" + "=" * 50)
    print(">>> 启动 node_search_embedding_hyde 本地测试")
    print("=" * 50)

    # 模拟输入状态
    mock_state = {
        "session_id": "test_hyde_session_001",
        "original_query": "HAK 180 烫金机怎么操作？",
        "rewritten_query": "HAK 180 烫金机的具体操作步骤是什么？",
        "item_names": ["HAK 180 烫金机"],
        "is_stream": False
    }

    try:
        # 运行节点
        result = node_search_embedding_hyde(mock_state)

        print("\n" + "=" * 50)
        print(">>> 测试结果摘要:")
        print(f"HyDE Doc Generated: {bool(result.get('hyde_doc'))}")
        if result.get("hyde_doc"):
            print(f"Doc Preview: {result.get('hyde_doc')[:50]}...")

        chunks = result.get("hyde_embedding_chunks", [])
        print(f"Chunks Found: {len(chunks)} , chunks内容：{chunks}")
        if chunks:
            print(f"Top Chunk Score: {chunks[0].get('distance')}")
        print("=" * 50)

    except Exception as e:
        logger.exception(f"测试运行期间发生未捕获异常: {e}")