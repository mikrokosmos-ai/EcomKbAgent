import sys
import os
from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from pymilvus import DataType
from app.conf.milvus_config import milvus_config
# 导入自定义模块：
# 1. 流程状态载体：ImportGraphState为LangGraph流程的统一状态管理对象
from app.pipelines.import_pipeline.state import ImportGraphState
# 2. Milvus工具：获取单例Milvus客户端，实现连接复用
from app.clients.milvus_client import get_milvus_client
# 3. 大模型工具：获取大模型客户端，统一模型调用入口
from app.clients.llm_client import get_llm_client
# 4. 向量工具：BGE-M3模型实例、向量生成方法（稠密+稀疏向量）
from app.clients.embedding_client import get_bge_m3_ef, generate_embeddings
# 5. 任务工具：更新任务运行状态，用于任务监控和管理
from app.utils.task_utils import add_running_task, add_done_task
# 6. 日志工具：项目统一日志入口，分级输出（info/warning/error）
from app.core.logger import logger, node_log, step_log
# 7. 提示词工具：加载本地prompt模板，实现提示词与代码解耦
from app.prompts.loader import load_prompt


# --- 配置参数 (Configuration) ---
# 大模型识别商品名称的上下文切片数：取前5个切片，避免上下文过长导致大模型输入超限
DEFAULT_ITEM_NAME_CHUNK_K = 5
# 单个切片内容截断长度：防止单切片内容过长，占满大模型上下文
SINGLE_CHUNK_CONTENT_MAX_LEN = 800
# 大模型上下文总字符数上限：适配主流大模型输入限制，默认2500
CONTEXT_TOTAL_MAX_CHARS = 2500

@step_log("step_1_check_content")
def step_1_check_content(state):
    """
        获取chunks切片和对应file_title
        :param state:
        :return:
    """
    chunks = state['chunks']
    file_title = state['file_title']
    md_path = state['md_path']
    # 非空校验
    if not chunks:
        logger.error(f"chunks没有内容,无法继续业务!")
        raise ValueError("chunks没有内容,无法继续业务!")
    if not file_title:
        logger.warning("没有在state读取到file_title,计划给与默认值!")
        if md_path:
            file_title = Path(md_path).stem
        if not file_title:
            file_title = "default"
        state['file_title'] = file_title
    return chunks, file_title


@step_log("step_2_build_context")
def step_2_build_context(chunks) -> str:
    """
       根据切片内容,拼接context,提供给模型进行识别item_name
          chunks = [{title,content,file_title,part,parent_title},{},{}]   -> top k 切片 -> 文本 (context) -> user 提示词 -> lm
          chunks[:DEFAULT_ITEM_NAME_CHUNK_K]  -> 文本
             切片:1,标题:xxx,内容:xxx \n
             切片:2,标题:xxx,内容:xxx \n
             切片:3,标题:xxx,内容:xxx \n
             切片:4,标题:xxx,内容:xxx \n
             切片:5,标题:xxx,内容:xxx \n
         别超过我们最大的长度限额: CONTEXT_TOTAL_MAX_CHARS
       :param chunks:
       :return:
       """
    # 1. 截取topk
    current_chunks = chunks[:DEFAULT_ITEM_NAME_CHUNK_K]
    chunks_str_list = []
    # 2. 循环处理
    for index, item in enumerate(current_chunks, start=1):
        # 3. 进行每个chunk -> 字符串
        title = item.get("title", "")
        content = item.get("content", "")
        chunks_str_list.append(f"切片:{index},标题:{title},内容:{content}")

    # 4. 前五个chunk对应字符串 .join("\n")
    chunks_str = "\n".join(chunks_str_list)
    # 5. 检查最大的长度 CONTEXT_TOTAL_MAX_CHARS
    final_context = chunks_str[:CONTEXT_TOTAL_MAX_CHARS]
    # 6. 返回即可
    return final_context


@step_log("step_3_call_llm")
def step_3_call_llm(context, file_title) -> str:
    """
          调用 lm , 总结和获取 item_name,如果没有返回! 使用file_title
        :param context:
        :param file_title:
        :return:
    """
    # 1. 获取模型对象
    llm = get_llm_client()
    # 2. 拼接提示词
    system_prompt_str = load_prompt("product_recognition_system")
    user_prompt_str = load_prompt("item_name_recognition", file_title=file_title, context=context)

    messages = [
        SystemMessage(content=system_prompt_str),
        HumanMessage(content=user_prompt_str)
    ]
    # 3. 链式组装
    chain = llm | StrOutputParser()
    # 4. 调用并获取结果
    item_name = chain.invoke(messages)
    # 5. 结果校验
    if not item_name:
        item_name = file_title
    # 6. 返回结果
    return item_name


@step_log("step_4_update_chunks_and_state")
def step_4_update_chunks_and_state(state, item_name,chunks):
    """
        修改state和chunks
    """
    state['item_name'] = item_name
    for chunk in chunks:
        chunk['item_name'] = item_name
    state['chunks'] = chunks


@step_log("step_5_generate_embeddings")
def step_5_generate_embeddings(item_name):
    """
    根据生成向量 -> 稠密 + 稀疏
    :param item_name:
    :return:  dense_vector[稠密], sparse_vector[稀疏]
    """
    vectors = generate_embeddings([item_name])  # 单文本需封装为列表，满足 generate_embeddings 的入参契约
    dense_vector = vectors['dense'][0]
    sparse_vector = vectors['sparse'][0]
    return dense_vector, sparse_vector


@step_log("step_6_insert_milvus")
def step_6_insert_milvus(item_name, file_title,dense_vector, sparse_vector):
    """
        将四个参数插入到对应milvus中即可! 一个实体  item_name, file_title, dense_vector, sparse_vector
    """
    # 1. 链接milvus的客户端
    milvus_client = get_milvus_client()
    # 2. 创建表对应schema [有哪些列和列的类型描述]
    if not milvus_client.has_collection(collection_name=milvus_config.item_name_collection):
        schema = milvus_client.create_schema(
            auto_id=True,  # id 数字 自增长
            enable_dynamic_field=True,  # 可以传入没有声明的字段
        )
        schema.add_field(field_name="pk", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=512)
        #dim 向量维度
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)

         # 3. 创建列对应的索引
        index_params = milvus_client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="AUTOINDEX",  # 根据我们的数据量自动切换索引类型 [只支持稠密向量]
            metric_type="IP"  # 稠密向量 COSINE(余弦) IP（内积） L2（欧式）  如果没有归一化 -> COSINE   归一化 -> COSINE == IP
        )
        index_params.add_index(
            field_name="sparse_vector",
            index_name="sparse_vector_index",
            index_type="SPARSE_INVERTED_INDEX",  # 只有一种索引
            metric_type="IP",  # 稀疏向量 IP 考虑我们词的权重和语气(模型) BM25  (es)
            params={"inverted_index_algo": "DAAT_MAXSCORE"}  # 跳过0 比较有值的位置
        )

         # 4. 创建集合collection
        milvus_client.create_collection(
            collection_name=milvus_config.item_name_collection,
            schema=schema,
            index_params=index_params,
        )

    #5.先删除之前存在的item_name
    milvus_client.delete(
        collection_name=milvus_config.item_name_collection,
        filter=f"item_name == '{item_name}'"
    )
    # 调用 load_collection() 会触发 Milvus 重新加载集合数据、刷新索引、清理已标记删除的数据，确保删除操作真正生效，避免新旧数据混杂导致检索错误。
    milvus_client.load_collection(collection_name=milvus_config.item_name_collection)

    # 6. 向集合插入最新的item_name数据和对应的向量即可
    data = [
        {
            "file_title": file_title,
            "item_name": item_name,
            "dense_vector": dense_vector,
            "sparse_vector": sparse_vector
        }
    ]
    #7. data对应的是列表 ,插入多条数据!!
    milvus_client.insert(collection_name=milvus_config.item_name_collection, data=data)


@node_log("node_item_name_recognition")
def node_item_name_recognition(state: ImportGraphState) -> ImportGraphState:
    """
     节点: 主体识别 (node_item_name_recognition)
    为什么叫这个名字: 识别文档核心描述的物品/商品名称 (Item Name)。
    1. 日志和任务添加
    2. 检查chunks和file_title
    3. chunks拼接了提示词的上下文
    4. 调用模型获取item_name,如果没有进行file_title兜底
    5. 修改state和chunks
    6. item_name生成稠密和稀疏向量
    7. 准备集合和插入数据milvus中
    8. 任务和日志处理
    """
    #1. 日志和任务添加
    add_running_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    #2. 检查chunks和file_title
    chunks, file_title = step_1_check_content(state)
    #3. chunks拼接了提示词的上下文
    context = step_2_build_context(chunks)
    #4. 调用模型获取item_name, 如果没有进行file_title兜底
    item_name = step_3_call_llm(context, file_title)
    #5. 修改state和chunks
    step_4_update_chunks_and_state(state, item_name,chunks)
    #6. item_name生成稠密和稀疏向量
    dense_vector, sparse_vector = step_5_generate_embeddings(item_name)
    #7. 准备集合和插入数据milvus中
    step_6_insert_milvus(item_name, file_title,dense_vector, sparse_vector)
    #8. 任务和日志处理
    add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    return state



# ===================== 本地测试方法（直接运行调试，无需启动LangGraph） =====================
def test_node_item_name_recognition():
    """
    商品名称识别节点本地测试方法
    功能：模拟LangGraph流程输入，独立测试node_item_name_recognition节点全链路逻辑
    适用场景：本地开发、调试、单节点功能验证，无需启动整个LangGraph流程
    测试前准备：
        1. 确保项目环境变量配置完成（MILVUS_URL/ITEM_NAME_COLLECTION等）
        2. 确保大模型、Milvus、BGE-M3服务均可正常访问
        3. 确保prompt模板（item_name_recognition/product_recognition_system）已存在
    使用方法：
        直接运行该函数：if __name__ == "__main__": test_node_item_name_recognition()
    """
    logger.info("=== 开始执行商品名称识别节点本地测试 ===")
    try:
        # 1. 构造模拟的ImportGraphState状态（模拟上游节点产出数据）
        mock_state = ImportGraphState({
            "task_id": "test_task_123456",  # 测试任务ID
            "file_title": "华为Mate60 Pro手机使用说明书",  # 模拟文件标题
            "file_name": "华为Mate60Pro说明书.pdf",  # 模拟原始文件名（兜底用）
            "md_path": "华为Mate60Pro说明书",  # 模拟 Markdown 路径（兜底用，补齐 ImportGraphState 契约，缺省为空串）
            # 模拟文本切片列表（上游切片节点产出，含title/content字段）
            "chunks": [
                {
                    "title": "产品简介",
                    "content": "华为Mate60 Pro是华为公司2023年发布的旗舰智能手机，搭载麒麟9000S芯片，支持卫星通话功能，屏幕尺寸6.82英寸，分辨率2700×1224。"
                },
                {
                    "title": "拍照功能",
                    "content": "华为Mate60 Pro后置5000万像素超光变摄像头+1200万像素超广角摄像头+4800万像素长焦摄像头，支持5倍光学变焦，100倍数字变焦。"
                },
                {
                    "title": "电池参数",
                    "content": "电池容量5000mAh，支持88W有线超级快充，50W无线超级快充，反向无线充电功能。"
                }
            ]
        })

        # 2. 调用商品名称识别核心节点
        result_state = node_item_name_recognition(mock_state)

        # 3. 打印测试结果（调试用）
        logger.info("=== 商品名称识别节点本地测试完成 ===")
        logger.info(f"测试任务ID：{result_state.get('task_id')}")
        logger.info(f"最终识别商品名称：{result_state.get('item_name')}")
        logger.info(f"切片数量：{len(result_state.get('chunks', []))}")
        logger.info(f"第一个切片商品名称：{result_state.get('chunks', [{}])[0].get('item_name')}")

        # 4. 验证Milvus存储（可选）
        milvus_client = get_milvus_client()
        collection_name = os.environ.get("ITEM_NAME_COLLECTION")
        if milvus_client and collection_name:
            milvus_client.load_collection(collection_name)
            # 检索测试结果
            item_name = result_state.get('item_name')
            safe_name = item_name
            res = milvus_client.query(
                collection_name=collection_name,
                filter=f'item_name=="{safe_name}"',
                output_fields=["file_title", "item_name"]
            )
            logger.info(f"Milvus中检索到的数据：{res}")

    except Exception as e:
        logger.error(f"商品名称识别节点本地测试失败，原因：{str(e)}", exc_info=True)


# 测试方法运行入口：直接执行该文件即可触发测试
if __name__ == "__main__":
    # 执行本地测试
    test_node_item_name_recognition()





