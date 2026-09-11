import sys
from app.conf.query_pipeline_config import query_pipeline_config
from app.utils.task_utils import add_running_task, add_done_task
from app.core.logger import logger, node_log, step_log

# RRF 融合参数（来源：app/conf/query_pipeline_config.py，默认值等于改造前的默认参数值）
# k：平滑参数，用于削弱排名的过大影响
RRF_K = query_pipeline_config.rrf_k
# top：融合排序后保留的条数
RRF_TOP = query_pipeline_config.rrf_top


@step_log("step_1_data_validates")
def step_1_data_validates(state):
    """
    获取参数并且校验
    :param state:
    :return:
    """
    embedding_chunks = state.get("embedding_chunks", [])
    hyde_embedding_chunks = state.get("hyde_embedding_chunks", [])
    return embedding_chunks, hyde_embedding_chunks


@step_log("step_2_rrf_list")
def step_2_rrf_list(param_list, k: int = RRF_K, top: int = RRF_TOP):
    """
    进行多路融合排序 , 同源,启动算法!
    本次算法 = (1.0 / (k + rank)) * weight
    :param param_list: [([1 {id:xx,distance:xx,entity:{chunk_id}},2,3],1.0),([1,2,3],1.0),([],1.0)]
    :param k 平滑参数,用于削弱排名的过大影响（默认取配置 RRF_K）
    :param top 最终的获取数量（默认取配置 RRF_TOP）
    :return: [entity,entity....]
    """
    # 1. 定义两个字典( 分别存储chunk_id，累计得分  || chunk_id  chunk entity )
    score_dict = {}  # key ：chunk_id |  value ：score
    entity_dict = {}  # key ：chunk_id |  value ：chunk entity
    # 2. 循环路 (计算每一路的分 )
    for chunks_list, weight in param_list:
        # 3. 循环单路的积分 (排名第一开始处理)
        for rank, chunk in enumerate(chunks_list, start=1):
            # rank排名 1 2 3  = chunk 数据
            # {id:xx,distance:分 , entity:{chunk_id:xx }}
            # {chunk_id:xx  }
            chunk_id = chunk.get("id") or chunk['entity']['chunk_id']
            # 获取之前的分 + 本次的分
            score_dict[chunk_id] = score_dict.get(chunk_id, 0.0) + (1.0 / (k + rank)) * weight
            # 存储chunk_id -> entity
            # 每次都赋值,下一次覆盖上一次!
            # entity_dict[chunk_id] = chunk.get("entity",{})
            # 如果没有值,才赋值! 第一次已经赋值了,后面就不会更新了
            entity_dict.setdefault(chunk_id, chunk.get("entity", {}))
    # 4. 处理数据和排序
    # score_dict = {1:0.8,2:0.5,3:0.9}
    #  => [(entity,score),(entity,score),(entity,score)] -> sort(key lambda x:x[1] , re = True)
    # entity_dict = {1:{},2:{},3:{}}
    entity_list = []
    for chunk_id, score in score_dict.items():
        entity_list.append(
            (
                entity_dict.get(chunk_id, {}),
                score
            )
        )
    # [(entity,score 高分) ...... ]
    entity_list.sort(key=lambda x: x[1], reverse=True)
    final_entity_list = [entity for entity, score in entity_list[:top]]
    # 5. 返回结果即可
    return final_entity_list


@node_log("node_rrf")
def node_rrf(state):
    """
    节点功能：Reciprocal Rank Fusion
    将多路召回的结果（向量、HyDE、Web、KG）进行加权融合排序。
    """
    # 1. 日志+任务
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state.get("is_stream"))
    # 2. 参数获取和校验 embedding_chunks hyde_embedding_chunks  get("key",[])
    embedding_chunks, hyde_embedding_chunks = step_1_data_validates(state)
    # 3. 处理下集合参数 [(embedding_chunks,1.0),(hyde_embedding_chunks,1.0)]  -> param_list
    param_list = [
        (embedding_chunks, 1.0),
        (hyde_embedding_chunks, 1.0)
    ]
    # 4. 定义个rrf+权重排序的函数  param_list  -> rrf_chunks
    """
        [
            [
               {
                  id: chunk_id,
                  distance: 0.6,
                  entity: {output_field chunk_id , title , file_title , parent_title , part , item_name , content}
               }

            ]  , 1.0 

             [
               {
                  id: chunk_id,
                  distance: 0.6,
                  entity: {output_field chunk_id , title , file_title , parent_title , part , item_name , content}
               }

            ]  , 1.0 
        ]
        [{output_field chunk_id , title , file_title , parent_title , part , item_name , content},{output_field chunk_id , title , file_title , parent_title , part , item_name , content}{output_field chunk_id , title , file_title , parent_title , part , item_name , content}]

    """
    entity_list = step_2_rrf_list(param_list)
    # 5.更新结果
    state["rrf_chunks"] = entity_list
    # ...
    add_done_task(state['session_id'], sys._getframe().f_code.co_name, state.get("is_stream"))
    return state



# ================================
# 本地测试入口
# ================================
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(">>> 启动 node_rrf 本地测试")
    print("=" * 50)

    mock_state = {
        "session_id": "test_rrf_session",
        "is_stream": False,
        "original_query": "HAK 180 烫金机怎么操作？",
        "rewritten_query": "HAK 180 烫金机的具体操作步骤是什么？",
        "item_names": ["HAK 180 烫金机"]
    }

    try:
        from app.pipelines.query_pipeline.nodes.node_search_embedding import node_search_embedding
        from app.pipelines.query_pipeline.nodes.node_search_embedding_hyde import node_search_embedding_hyde

        emb_res = node_search_embedding(mock_state)
        hyde_res = node_search_embedding_hyde(mock_state)
        mock_state['embedding_chunks'] = emb_res.get("embedding_chunks") or []
        mock_state['hyde_embedding_chunks'] = hyde_res.get("hyde_embedding_chunks") or []

        result = node_rrf(mock_state)
        rrf_chunks = result.get("rrf_chunks", [])

        emb_cnt = len(mock_state.get("embedding_chunks") or [])
        hyde_cnt = len(mock_state.get("hyde_embedding_chunks") or [])

        print("\n" + "=" * 50)
        print(">>> 测试结果摘要:")
        print(f"输入数量: Embedding={emb_cnt}, HyDE={hyde_cnt}")
        print(f"输出数量: {len(rrf_chunks)}")
        print("-" * 30)

        print("最终排名:")
        for i, doc in enumerate(rrf_chunks, 1):
            doc_id = doc.get("chunk_id") or doc.get("id")
            content = (doc.get("content") or "")[:20]
            print(f"Rank {i}: ID={doc_id}, Content={content}...")

        print("=" * 50)

    except Exception as e:
        logger.exception(f"测试运行期间发生未捕获异常: {e}")