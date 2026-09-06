# 导入Milvus相关依赖
import sys
from pymilvus import DataType
# 导入自定义模块
from app.pipelines.import_pipeline.state import ImportGraphState
from app.clients.milvus_client import get_milvus_client
from app.utils.task_utils import add_running_task, add_done_task
from app.core.logger import logger, node_log, step_log
from app.conf.milvus_config import milvus_config

# 从配置文件读取切片集合名称，与配置解耦，便于环境切换
CHUNKS_COLLECTION_NAME = milvus_config.chunks_collection


@step_log("step_1_validate_chunks")
def step_1_validate_chunks(state):
    """
    参数校验
    :param state:
    :return:
    """
    chunks = state["chunks"]
    if not chunks or len(chunks) == 0:
        logger.error(f"chunks为空,无法继续业务!!")
        raise ValueError(f"chunks为空,无法继续业务!!")
    return chunks


@step_log("step_2_prepare_collection")
def step_2_prepare_collection():
    """
        准备集合
        :return:
    """
    # 1. 获取mivlus客户端
    milvus_client = get_milvus_client()
    # 2. 判断是否存在,不存在进行创建流程
    if not milvus_client.has_collection(collection_name=CHUNKS_COLLECTION_NAME):
        # 创建schema filed
        schema = milvus_client.create_schema(
            auto_id=True,
            enable_dynamic_field=True,
        )
        # schema添加字段
        schema.add_field(field_name="chunk_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="parent_title", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="part", datatype=DataType.INT8)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)

        # 3. 创建列对应的索引
        index_params = milvus_client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="AUTOINDEX",  # 根据我们的数据量自动切换索引类型 [只支持稠密向量]
            metric_type="IP"  # 稠密向量 COSINE IP L2  如果没有归一化 -> COSINE 归一化 =  COSINE == IP
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
            collection_name=CHUNKS_COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )


@step_log("step_3_delete_old_data")
def step_3_delete_old_data(state):
    """
       删除旧数据 根据item_name删除
       :param state:
       :return:
    """
    milvus_client = get_milvus_client()
    item_name = state['item_name']
    milvus_client.delete(collection_name=CHUNKS_COLLECTION_NAME,
                         filter=f"item_name=='{item_name}'")
    # 调用 load_collection() 会触发 Milvus 重新加载集合数据、刷新索引、清理已标记删除的数据，确保删除操作真正生效，避免新旧数据混杂导致检索错误。
    milvus_client.load_collection(collection_name=CHUNKS_COLLECTION_NAME)


@step_log("step_4_insert_datas")
def step_4_insert_datas(chunks):
    """
       插入集合的数据！
       :param chunks:
       :return:  chunks -> 主键回显
       """
    milvus_client = get_milvus_client()
    result = milvus_client.insert(
        collection_name=CHUNKS_COLLECTION_NAME,
        data=chunks
    )
    insert_count = result.get("insert_count", 0)
    logger.info(f"插入数据成功! 总条数:{insert_count}")
    # 获取回显的ids
    ids = result.get("ids", [])
    if ids and len(ids) == len(chunks):
        for index, chunk in enumerate(chunks):
            chunk['chunk_id'] = ids[index]

    return chunks


@node_log("node_import_milvus")
def node_import_milvus(state: ImportGraphState) -> ImportGraphState:
    """
        作用: 就是chunks存到milvus!
        入参: chunks
        出参: 不报错
        步骤:
              1. 日志+任务处理
              2. 参数校验(chunks不为空)
              3. 如果没有准备集合,我们创建集合(集合 schema indexs...)
              4. 删除旧数据根据item_name
              5. 插入本次的数据集合
              6. 日志+任务处理
    """
    # 1. 日志+任务处理
    add_running_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    # 2. 参数校验 chunks
    chunks = step_1_validate_chunks(state)
    # 3. 准备milvus的集合
    step_2_prepare_collection()
    # 4. 删除旧数据
    step_3_delete_old_data(state)
    # 5. 插入新数据
    step_4_insert_datas(chunks)
    # 6. 日志+任务处理
    add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    return state


if __name__ == '__main__':
    # --- 单元测试 ---
    # 目的：验证 Milvus 导入节点的完整流程，包括连接、创建集合、清理旧数据和插入新数据。
    import os
    from dotenv import load_dotenv

    # 加载环境变量 (自动寻找项目根目录的 .env)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    load_dotenv(os.path.join(project_root, ".env"))

    # 构造测试数据
    dim = 1024
    test_state = {
        "task_id": "test_milvus_task",
        "item_name": "测试项目_Milvus",
        "chunks": [
            {
                "content": "Milvus 测试文本 1",
                "title": "测试标题",
                "item_name": "测试项目_Milvus",  # 必须有 item_name，用于幂等清理
                "parent_title": "test.pdf",
                "part": 1,
                "file_title": "test.pdf",
                "dense_vector": [0.1] * dim,  # 模拟 Dense Vector
                "sparse_vector": {1: 0.5, 10: 0.8}  # 模拟 Sparse Vector
            }
            ,
            {
                "content": "Milvus 测试文本 2",
                "title": "测试标题2",
                "item_name": "测试项目_Milvus2",  # 必须有 item_name，用于幂等清理
                "parent_title": "test.pdf2",
                "part": 1,
                "file_title": "test.pdf2",
                "dense_vector": [0.1] * dim,  # 模拟 Dense Vector
                "sparse_vector": {1: 0.5, 10: 0.8}  # 模拟 Sparse Vector
            }
        ]
    }

    print("正在执行 Milvus 导入节点测试...")
    try:
        # 检查必要的环境变量
        if not os.getenv("MILVUS_URL"):
            print("❌ 未设置 MILVUS_URL，无法连接 Milvus")
        elif not os.getenv("CHUNKS_COLLECTION"):
            print("❌ 未设置 CHUNKS_COLLECTION")
        else:
            # 执行节点函数
            result_state = node_import_milvus(test_state)

            # 验证结果
            chunks = result_state.get("chunks", [])
            logger.info(f"返回结果:{chunks}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")