import sys
from pathlib import Path
from app.core.logger import logger, node_log
from app.pipelines.import_pipeline.state import ImportGraphState, create_default_state
from app.utils.task_utils import add_running_task, add_done_task

"""
  入参:  local_file_path / task_id
  出参:  is_md_read_enabled is_pdf_read_enabled  md_path  pdf_path  file_title 
  步骤:
       0. 日志动作  @node_log + 任务列表记录 (进行中,已完成)
       1. 获取state中数据 local_file_path task_id
       2. 进行文件校验 local_file_path 是否为空
       3. 根据地址判断文件类型,修改对应的state参数即可
       4. 识别文件地址对应的文件名称
       5. 返回结果和状态 
"""
@node_log("node_entry")
def node_entry(state: ImportGraphState) -> ImportGraphState:
    """
       节点: 入口节点 (node_entry)
       为什么叫这个名字: 作为图的 Entry Point，负责接收外部输入并决定流程走向。
       """
    # 0. 设置成进行中任务
    add_running_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))

    # 1. 获取state中数据 local_file_path task_id
    local_file_path = state['local_file_path']
    # 2. 校验是否为空(不需要考虑是否真的有文件,读取文件内容的时候再考虑)
    if not local_file_path:
        logger.warning(f"没有输入文件地址,无法处理,直接跳转到结束节点!")
        add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
        return state
    # 3. 根据地址判断文件类型,修改对应的state参数即可
    if local_file_path.endswith(".md"):
        # 处理md
        state['is_md_read_enabled'] = True
        state['md_path'] = local_file_path
    elif local_file_path.endswith(".pdf"):
        # 处理pdf
        state['is_pdf_read_enabled'] = True
        state['pdf_path'] = local_file_path
    else:
        logger.warning(f"虽然local_file_path有值{local_file_path},不是md或者pdf类型,所以无法识别,直接跳转到END节点!")
        add_done_task(state["task_id"], sys._getframe().f_code.co_name, state.get("is_stream", False))
        return state
    # 4. 是md/pdf并且已经修改对应的值,识别文件的名字
    file_title = Path(local_file_path).stem
    state['file_title'] = file_title

    # 5. 执行完毕
    add_done_task(state["task_id"], sys._getframe().f_code.co_name, state.get("is_stream", False))
    return state


if __name__ == '__main__':
    # 单元测试：覆盖不支持类型、MD、PDF三种场景
    logger.info("===== 开始node_entry节点单元测试 =====")

    # 测试1: 不支持的TXT文件
    test_state1 = create_default_state(
        task_id="test_task_001",
        local_file_path="联想海豚用户手册.txt"
    )
    node_entry(test_state1)

    logger.info(f"测试1结果: {test_state1}")

    # 测试2: MD文件
    test_state2 = create_default_state(
        task_id="test_task_002",
        local_file_path="小米用户手册.md"
    )
    node_entry(test_state2)

    logger.info(f"测试2结果: {test_state2}")

    # 测试3: PDF文件
    test_state3 = create_default_state(
        task_id="test_task_003",
        local_file_path="万用表的使用.pdf"
    )
    node_entry(test_state3)
    logger.info(f"测试3结果: {test_state3}")

    logger.info("===== 结束node_entry节点单元测试 =====")




