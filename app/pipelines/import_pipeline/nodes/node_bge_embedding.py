import sys
from app.conf.import_pipeline_config import import_pipeline_config
from app.pipelines.import_pipeline.state import ImportGraphState
from app.clients.embedding_client import generate_embeddings
from app.utils.task_utils import add_running_task, add_done_task
from app.core.logger import logger, node_log, step_log

# 切片向量化的批大小（来源：app/conf/import_pipeline_config.py，默认值等于改造前的字面量 5）
EMBEDDING_BATCH_SIZE = import_pipeline_config.embedding_batch_size

@step_log("step_1_validate_chunks")
def step_1_validate_chunks(state):
    """
    进行chunks非空校验
    :param state:
    :return: 校验完毕的chunks
    """
    # 1. 获取chunks
    chunks = state['chunks']
    # 2. 非空校验
    if not chunks or len(chunks) == 0:
        logger.error(f"发现chunks为空,无法继续业务处理!")
        raise ValueError("chunks为空,无法继续业务处理!")
    return chunks


@step_log("step_2_embedding_chunks")
def step_2_embedding_chunks(chunks):
    """
    为了给chunks生成向量
       1. 批量生成
       2. 增强生成 item_name + content
       3. 批量防止异常全体报错
    :param chunks:
    :return:
    """
    # 1. 数据准备工作(定义接收最终chunk列表,当前chunks total,声明一个批大小变量)
    chunks_vector = []
    total = len(chunks)
    step = EMBEDDING_BATCH_SIZE
    # 2. 批量处理chunks -> 5
    for index in range(0, total, step):
        try:
            # 3. 获取本次批量处理的chunks
            # [{title:xx, content:xx, item_name:""}]
            step_chunks = chunks[index:index + step]
            # 4.定义存储生成向量的字符串容器
            vectorx_str_list = []
            # 5.chunk -> str -> vector_str_list
            for item in step_chunks:
                # 拼接的格式  主体:{item_name},内容:{content} 核心内容前置!
                item_name = item['item_name']
                content = item['content']
                item_str = f"主体:{item_name},内容:{content}" if item_name else content
                vectorx_str_list.append(item_str)
            # 6. 生成向量
            result = generate_embeddings(vectorx_str_list)
            # 7. chunk的向量赋值
            for i, chunk in enumerate(step_chunks):
                chunk_new = chunk.copy()
                chunk_new['dense_vector'] = result['dense'][i]
                chunk_new['sparse_vector'] = result['sparse'][i]
                chunks_vector.append(chunk_new)
        except Exception as e:
            logger.warning(f"index= {index}步骤,发生错误,跳过,继续生成向量!!,错误信息:{str(e)}")
            continue
    # 8. 返回结果
    return chunks_vector


@node_log("node_bge_embedding")
def node_bge_embedding(state: ImportGraphState) -> ImportGraphState:
    """
    节点: 向量化 (node_bge_embedding)
    为什么叫这个名字: 使用 BGE-M3 模型将文本转换为向量 (Embedding)。
    未来要实现:
    1. 加载 BGE-M3 模型。
    2. 对每个 Chunk 的文本进行 Dense (稠密) 和 Sparse (稀疏) 向量化。
    3. 准备好写入 Milvus 的数据格式。
    """
    # 1.日志+任务处理
    add_running_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    # 2.参数校验chunks
    chunks = step_1_validate_chunks(state)
    # 3.批量生成向量 chunks
    chunks_vector = step_2_embedding_chunks(chunks)
    # 4.chunks修改state
    state['chunks'] = chunks_vector
    # 5.日志+任务处理
    add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    return state



# ==========================================
# 本地单元测试入口
# 功能：独立验证向量化节点全链路逻辑，无需启动整个LangGraph流程
# 适用场景：本地开发、调试、模型有效性验证
# ==========================================
if __name__ == '__main__':
    import os
    from dotenv import load_dotenv
    # 加载环境变量：定位项目根目录下的.env，读取模型路径/设备等配置
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    load_dotenv(os.path.join(project_root, ".env"))

    # 构造模拟测试状态：模拟上游节点输出的chunks数据，贴合真实业务场景
    test_state = ImportGraphState({
        "task_id": "test_task_embedding_001",  # 测试任务ID
        "chunks": [  # 模拟带item_name的文本切片（上游商品名称识别节点产出）
            {
                "content": "这是一个测试文档的内容，用于验证向量化是否成功。",
                "title": "测试文档标题",
                "item_name": "测试项目",
                "file_title": "测试文件.pdf"
            },
            {
                "content": "这是第二个测试文档的内容，用于验证批量处理逻辑。",
                "title": "测试文档标题2",
                "item_name": "测试项目",
                "file_title": "测试文件.pdf"
            }
        ]
    })

    # 执行本地测试
    logger.info("=== BGE-M3向量化节点本地单元测试启动 ===")
    try:
        # 调用核心节点函数
        result_state = node_bge_embedding(test_state)
        # 提取测试结果
        result_chunks = result_state.get("chunks", [])

        # 打印测试结果统计
        logger.info(f"=== 向量化节点本地测试完成 ===")
        logger.info(f"测试任务ID：{test_state.get('task_id')}")
        logger.info(f"待处理切片数：2 | 实际处理切片数：{len(result_chunks)}")
        logger.info(f"返回的结果:{result_chunks}")


    except Exception as e:
        logger.error(f"=== 向量化节点本地测试失败 ===" f"错误原因：{str(e)}", exc_info=True)
        # 新手友好提示：给出核心排查方向
        logger.warning("排查提示：请检查BGE-M3模型路径、显存是否充足、环境变量配置是否正确")