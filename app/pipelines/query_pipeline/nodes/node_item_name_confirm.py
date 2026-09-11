import sys
import json
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from app.conf.milvus_config import milvus_config
from app.prompts.loader import load_prompt

from app.utils.task_utils import add_running_task, add_done_task
from app.repositories.history_repo import get_recent_messages, save_chat_message
from app.clients.llm_client import get_llm_client
from app.clients.embedding_client import generate_embeddings
from app.clients.milvus_client import get_milvus_client
from app.repositories.vector_search_repo import create_hybrid_search_requests, hybrid_search
from dotenv import load_dotenv, find_dotenv
from app.core.logger import logger, node_log, step_log
from app.conf.query_pipeline_config import query_pipeline_config

load_dotenv(find_dotenv())

# ====================== 商品名确认参数（来源：app/conf/query_pipeline_config.py）======================
# 说明：以下常量仅作为配置项的模块级别名，默认值等于改造前的字面量现值；
#       可用同名环境变量覆盖，详见配置文件。
# 高置信阈值：达到即确认为该商品名
ITEM_NAME_HIGH_THRESHOLD = query_pipeline_config.item_name_high_threshold
# 中置信阈值：介于中/高阈值之间时，转入"待用户确认"分支
ITEM_NAME_MID_THRESHOLD = query_pipeline_config.item_name_mid_threshold
# 待确认时最多给出的候选数量
ITEM_NAME_MAX_OPTIONS = query_pipeline_config.item_name_max_options
# 商品名向量匹配的稠密/稀疏权重
ITEM_NAME_MATCH_WEIGHTS = (
    query_pipeline_config.item_name_match_dense_weight,
    query_pipeline_config.item_name_match_sparse_weight,
)


@step_log("step_1_data_validates")
def step_1_data_validates(state):
    """
    获取session_id和原始查询内容,并且进行校验处理!
    :param state:
    :return:
    """
    original_query = state.get("original_query")
    session_id = state.get("session_id")
    if not original_query or not session_id:
        logger.error(f"session_id和original_query不能为空")
        raise ValueError("session_id和original_query不能为空")
    return original_query, session_id


@step_log("step_2_chat_history")
def step_2_chat_history(session_id):
    """历史聊天记录"""
    return get_recent_messages(session_id)


@step_log("step_3_llm_itemnames_and_rewrite")
def step_3_llm_itemnames_and_rewrite(history_chats, original_query):
    """
    进行item_name和rewritten_query识别
    :param history_message_list:
    :param original_query:
    :return:  {item_names:[],rewritten_query:重写问题}
    """
    # 1. 初始化模型对象
    llm_client = get_llm_client(json_mode=True)
    # 2. 进行提示词处理
    history_text = ""
    for msg in history_chats:
        history_text += \
            (f"角色:{msg['role']},内容:{msg['rewritten_query'] if msg['role'] == 'user' else msg['text']}"
             f",关联主体: {'、'.join(msg['item_names'])}\n")
    prompt = load_prompt("rewritten_query_and_itemnames", history_text=history_text, query=original_query)
    # 3. 组装提示词调用链
    messages = [
        SystemMessage(content="你是一个专业的客服助手，擅长理解用户意图和提取关键信息。"),
        HumanMessage(content=prompt)
    ]
    chain = llm_client | JsonOutputParser()
    # 4. 执行并获取json结果
    llm_json_dict = chain.invoke(messages)

    if not "rewritten_query" in llm_json_dict:
        logger.warning(f"模型重写问题失败,给rewritten_query赋予原始问题:{original_query}")
        llm_json_dict["rewritten_query"] = original_query
    if not "item_names" in llm_json_dict:
        logger.warning(f"模型识别商品失败,给item_names赋予空列表")
        llm_json_dict["item_names"] = []
    # 5. 返回结果即可
    return llm_json_dict


@step_log("step_4_vector_query_item_name")
def step_4_vector_query_item_name(item_names):
    """
          a -> 向量 -> 两个annSearchRequest -> hy_search -> 结果
          b -> 向量 -> 两个annSearchRequest -> hy_search -> 结果
          c -> 向量 -> 两个annSearchRequest -> hy_search -> 结果
          d -> 向量 -> 两个annSearchRequest -> hy_search -> 结果
       :param item_names:  lm : [a,b,c,d]
       :return:
          {
             a : [{item_name:xx,score:0.8}]
          }
       """
    #获取milvus客户端
    milvus_client = get_milvus_client()
    query_milvus_results = {}
    # 1. 将lm查询到的item_name转化成向量
    # result = {dense:[],sparse:[]}
    item_name_dict = generate_embeddings(item_names)
    # 2. 循环每个item_name对应稠密和稀疏向量,进行混合查询
    for index in range(len(item_names)):
        # index 获取当前item_name对应的稠密和稀疏向量
        dense_vector = item_name_dict["dense"][index]
        sparse_vector = item_name_dict["sparse"][index]
        # 将稠密和稀疏向量分别转成annSearchRequest
        reqs = create_hybrid_search_requests(dense_vector, sparse_vector)
        # 调用混合检索函数进行搜索结果
        response = hybrid_search(
            client=milvus_client,
            collection_name=milvus_config.item_name_collection,
            reqs=reqs,
            ranker_weights=ITEM_NAME_MATCH_WEIGHTS,  # 稠密/稀疏权重（配置项，默认 0.5 / 0.5）
            norm_score = True,      # 将分调整到 0 - 1 之间比较
            output_fields=["item_name"]
        )
        # 3. 解析结果
        current_item_name = []
        for item in response[0]:
            """
             {
                id:xx,
                distance:0.8,
                entity:{item_name:向量中item_name}
            }
            """
            current_item_name.append(
                {
                    "item_name": item.get("entity", {}).get("item_name", ""),
                    "score": item.get("distance", 0)
                }
            )
        # 4. 装到最终dict
        query_milvus_results[item_names[index]] = current_item_name
    # 5. 最终返回结果
    return query_milvus_results


@step_log("step_5_select_item_name_list")
def step_5_select_item_name_list(query_milvus_results):
    """
    作用: 在向量查询的列表中,选出确定和可选的item_name列表
    final_result = {confirmed_item_name_list:[],options_item_name_list:[]}

    { A: [{item_name:匹配到的item_name,score:0.8},{item_name:匹配到的item_name,score:0.8},{item_name:匹配到的item_name,score:0.8}]
      B: [{item_name:匹配到的item_name,score:0.8},{item_name:匹配到的item_name,score:0.8},{item_name:匹配到的item_name,score:0.8}]
      C: [{item_name:匹配到的item_name,score:0.8},{item_name:匹配到的item_name,score:0.8},{item_name:匹配到的item_name,score:0.8}]

    原则1: 每个模型提供item_name只能对应一个确认的向量查询item_name
    原则2: 当没有确认的item_name我们提取可以选的item_name 可选的每个提供至多两个2
    原则3: 他们最终不会区分,都会一起加入到 confirmed_item_name_list | options_item_name_list
        确认的规则:
             大于等于 ITEM_NAME_HIGH_THRESHOLD 入选 (配置项，默认 0.65，可按语料调整)
             只有一个 -> 就选他
             有多个  -> 选item_name (lm)  -> 最高分
        可选的规则: (没有确定)
             ITEM_NAME_MID_THRESHOLD <= 分数 < ITEM_NAME_HIGH_THRESHOLD
             提供 top ITEM_NAME_MAX_OPTIONS 个（配置项，默认 2）
        分更低: 就是无用的数据 不需要处理...

    :param vector_dict:
    :return:
    """
    # 1. 准备两个集合 确认 和 可选的
    confirmed_item_name_list = []
    options_item_name_list = []
    # 2. 遍历每个item_name对应向量数据
    for item_name, item_name_list in query_milvus_results.items():
        # 3. 排序. ..
        item_name_list.sort(key=lambda x: x["score"], reverse=True)
        # 4. 截取确认的集合和可选的集合
        high_list = [item for item in item_name_list if item["score"] >= ITEM_NAME_HIGH_THRESHOLD]
        low_list = [item for item in item_name_list
                    if ITEM_NAME_MID_THRESHOLD <= item["score"] < ITEM_NAME_HIGH_THRESHOLD]
        # 5. 确认集合长度和选择 确定一个
        # 只获取分数最高的
        if len(high_list) > 0:
            confirmed_item_name_list.append(high_list[0]["item_name"])
            continue
        # 6. 可选集合在确认集合没有选中的场景下,进行可选集合处理
        if len(low_list) > 0:
            options_item_name_list.extend(
                [item['item_name'] for item in low_list[:ITEM_NAME_MAX_OPTIONS]]
            )
    # 7. 返回结果
    return {
        "confirmed_item_name_list": confirmed_item_name_list,
        "options_item_name_list": options_item_name_list
    }


@step_log("step_6_deal_state")
def step_6_deal_state(state, final_result, rewritten_query, history_chats):
    """
    修改state : answer  item_names rewritten_query
    :param state:
    :param final_result:
    :param rewritten_query:
    :return:
    """
    confirmed_item_name_list = final_result.get("confirmed_item_name_list", [])
    options_item_name_list = final_result.get("options_item_name_list", [])
    # 1. 判断确定列表有没有数据 (有 皆大欢喜)
    if len(confirmed_item_name_list) > 0:
        state['item_names'] = confirmed_item_name_list
        state['rewritten_query'] = rewritten_query
        state['history'] = history_chats
        if "answer" in state:
            del state["answer"]
        return state
    # 2. 没有确定列表,有可选列表 (失败,提示可选....让对方确认..)
    if len(options_item_name_list) > 0:
        # 没有确认的有可选的
        # 名字、xxxx
        option_name_str = "、".join(options_item_name_list)
        state["answer"] = f"您是想问以下哪个产品：{option_name_str}？请明确一下型号。"
        return  state
    # 3. 可选都没有,无法确定无法可选,给与提示,明确即可
    state["answer"] = "抱歉，未找到相关产品，请提供准确型号以便我为您查询。"
    # 统一返回契约：三条分支都返回 state，避免出现"部分分支返回、部分分支隐式返回 None"的不一致
    return state


@step_log("step_7_save_user_chat_message")
def step_7_save_user_chat_message(state):
    # 进行用户聊天记录保存
    save_chat_message(
        session_id=state["session_id"],
        role="user",
        text=state["original_query"],
        rewritten_query=state["rewritten_query"],
        item_names=state["item_names"]
    )


@node_log("node_item_name_confirm")
def node_item_name_confirm(state):
    """
    节点功能：确认用户问题中的核心商品名称。
    输入：state['original_query']
    输出：更新 state['item_names']
    """
    #  1. 日志和任务处理 is_stream
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    #  2. 取值和校验 (original_query | session_id)  step_1  raise ValueError
    original_query, session_id = step_1_data_validates(state)
    #  3. 获取历史聊天记录(session_id) => list[message]
    history_chats = step_2_chat_history(session_id)
    #  4. 调用模型进行问题重写和item_name识别 (list[message],original_query) -> {item_names:[], rewritten_query:xx}
    llm_result_dict = step_3_llm_itemnames_and_rewrite(history_chats, original_query)
    item_names = llm_result_dict['item_names']
    rewritten_query = llm_result_dict['rewritten_query']
    if item_names and len(item_names) > 0:
        #  5. 通过模型提供的item_names分别进行向量数据库混合检索
        query_milvus_results = step_4_vector_query_item_name(item_names)
        #  6. 确认item_name列表
        final_result = step_5_select_item_name_list(query_milvus_results)
    else:
        # 兜底分支：LLM 未提取到任何商品名（属于正常业务场景，例如用户只问"这个怎么用？"且无历史上下文）。
        # 必须显式给出"空结果"，否则下面的 step_6 会因 final_result 未定义而抛 NameError，
        # 把本应走"未找到相关产品"提示的正常提问变成 500。
        logger.warning("LLM 未提取到任何商品名，跳过向量匹配，直接进入兜底提示分支")
        final_result = {"confirmed_item_name_list": [], "options_item_name_list": []}
    # 7.判断确定和可选的列表,最终处理answer以及给state
    step_6_deal_state(state, final_result, rewritten_query, history_chats)
    # 8.保存本次对话的记录(user)
    step_7_save_user_chat_message(state)
    # 记录任务结束
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    return state



if __name__ == "__main__":
    # 模拟输入状态
    mock_state = {
        "session_id": "test_session_001",
        "original_query": "HAK 180 烫金机请在什么下环境使用?",
        "is_stream": False
    }

    print(">>> 开始测试 node_item_name_confirm...")
    try:
        # 运行节点
        result_state = node_item_name_confirm(mock_state)

        print("\n>>> 测试完成！最终状态:")
        print(json.dumps(result_state, indent=2, ensure_ascii=False))

        # 简单验证
        if result_state.get("item_names"):
            print(f"\n[PASS] 成功提取并确认商品名: {result_state['item_names']}")
        else:
            print(f"\n[WARN] 未确认到商品名 (可能是向量库无匹配或LLM未提取)")

    except Exception as e:
        print(f"\n[FAIL] 测试运行出错: {e}")