import sys
import json
import os
import re
from pathlib import Path
from typing import Tuple, List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.logger import logger, node_log, step_log
from app.pipelines.import_pipeline.state import ImportGraphState
from app.utils.task_utils import add_running_task, add_done_task

# ====================== 全局配置（可根据模型调整）======================
CHUNK_MAX_SIZE = 500  # 500字符串 触发二次切割!
# 单个文本块最大长度（控制不超过模型上下文）
CHUNK_SIZE = 200   # 小值方便测试切割
# 块之间重叠长度（保证语义不丢失）
CHUNK_OVERLAP = 20
# 最小文本块长度（低于此值的相邻块将被合并,避免切分过碎）
CHUNK_MIN_SIZE = 100

@step_log("step_1_validate_clean")
def step_1_validate_clean(state) -> Tuple[str, str]:
    """
        1. 获取数据  md_content , file_title , md_path
        2. md_content进行非空校验 空->异常
        3. md_content不为空 -> 数据清洗 -> 字符串统一替换
        4. file_title进行非空判断 -> 空 -> 通过md_path获取file_title
        5. 返回数据即可
        :param state:
        :return:
    """
    md_content = state['md_content']
    file_title = state['file_title']
    md_path = state['md_path']

    # 进行必要非空校验
    if not md_content:
        logger.warning(f"没有从state读取到md_content内容,我们使用md_path尝试再次读取!")
        if md_path:
            md_content = Path(md_path).read_text(encoding='utf-8')
            state['md_content'] = md_content
        if not md_content:
            logger.error(f"md_content没数据,并且尝试读取md_path依然没有数据,终止执行!!")
            raise ValueError("md_content没数据,并且尝试读取md_path依然没有数据,终止执行!!")
    if not file_title:
        logger.warning("没有在state读取到file_title,计划给与默认值!")
        if md_path:
            file_title = Path(md_path).stem
        if not file_title:
            file_title = "default"
        state['file_title'] = file_title
    # md_content内容进行清洗
    md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
    # 返回结果
    return md_content, file_title

@step_log("step_2_split_by_title")
def step_2_split_by_title(md_content, file_title) -> List[Dict[str, str]]:
    """
        语义切割,根据标题,进行内容切割!
        :param md_content:
        :param file_title:
        :return: [{content,title,file_title}]
    """
    #1. 定义正则
    rep = re.compile(r"^\s*#{1,6}\s+.+")
    #2. 根据\n进行行的切割
    lines = md_content.split("\n")
    #3. 准备一些数据容器
    chunks = []                 #最终结果
    current_title = ""          #记录当前标题
    current_lines = []          #记录当前标题的正文行(不含标题行本身)
    pending_titles = []         #记录连续无正文的上级标题,待合并到下一个有正文的块
    is_code_block = False       #记录是否在代码块中
    title_count = 0

    #4. 循环处理每行数据
    for line in lines:
        #去掉空格
        strip_line = line.strip()
        #5. 检查是否进入和出去哪一行是不是代码块
        if strip_line.startswith('```') or strip_line.startswith('~~~'):
            is_code_block = not is_code_block
            current_lines.append(line)
            continue

        #6. 判断是不是标题 以及 不是代码块  -> 标题处理
        if re.match(rep, strip_line) and not is_code_block:
            #6.1 遇到新标题,先把上一个标题块落库
            if current_title:
                # 上一个标题有正文 -> 正常落库,并把pending_titles(空标题链)并入content开头
                if current_lines:
                    head = "\n".join(pending_titles + [current_title])
                    body = "\n".join(current_lines)
                    chunks.append({
                        "content": f"{head}\n{body}",
                        "title": current_title,
                        "file_title": file_title,
                    })
                    pending_titles = []
                # 上一个标题无正文 -> 空标题,暂存pending_titles,不生成空标题节点
                else:
                    pending_titles.append(current_title)
            # 第一个标题之前的前置内容 -> 非空则单独成块,避免丢失
            else:
                if any(ln.strip() for ln in current_lines):
                    chunks.append({
                        "content": "\n".join(current_lines),
                        "title": file_title,
                        "file_title": file_title,
                    })
            #6.2 切换到新标题,清空正文行
            current_title = strip_line
            current_lines = []
            title_count += 1
        #7. 不是代码块 也不是标题 -> 普通行处理
        else:
            current_lines.append(line)

    #8. 跳出循环后处理最后一个标题的内容
    if current_title:
        # 最后一个标题有正文 -> 正常落库(含pending_titles前缀)
        if current_lines:
            head = "\n".join(pending_titles + [current_title])
            body = "\n".join(current_lines)
            chunks.append({
                "content": f"{head}\n{body}",
                "title": current_title,
                "file_title": file_title
            })
            pending_titles = []
        # 最后一个标题无正文 -> 空标题,后无可合并正文,直接丢弃

    #9. 检查没有标题的文档 -> title default  md_content
    if title_count == 0:
        chunks.append({
            "content": md_content,
            "title": "default",
            "file_title": file_title
        })
        title_count = 1
    #10.返回结果
    logger.info(f"完成语义切割,切块数量:{len(chunks)},内容:{chunks[:3]}")
    return chunks


@step_log("step_3_data_refine_chunk")
def step_3_data_refine_chunk(chunks) -> List[Dict[str, str]]:
    """
       作用: 将超过执行size的标题内容,进行二次切分,二次切分产生: parent_title part
       入参: chunks
       出参: chunks   (part parent_title)
       步骤:
         1. 先定义langchain提供的递归切割器 [块大小,重叠部分,切割符号]
         2. 循环原来的chunks
         3. 获取每块的content长度
         4. 没有超过 -> 不需要二次切分 -> 补 part=0 parent_title
         5. 超过 -> 递归切割器 二次切割 -> part 从 1 递增
         6. 最终记录结果 final_chunks
         7. 循环结束后返回结果即可
       """
    #1. 先定义langchain提供的递归切割器 [块大小,重叠部分,切割符号]
    splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", "。", "！", "；", " ",""],  # 字符级切分
        chunk_size= CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )
    #2. 获取原来的chunks
    final_chunks = []
    for chunk in chunks:
        #3. 判断chunk content内容长度
        content = chunk['content']
        if len(content) > CHUNK_MAX_SIZE:
            #4. 超过阈值 -> 递归切割器 二次切割
            spliter_chunks = splitter.split_text(content)
            # 不变量守卫: 极端情况下(如 chunk_size 误配)仍可能存在超长块,记录告警避免静默透传
            for text in spliter_chunks:
                if len(text) > CHUNK_MAX_SIZE:
                    logger.warning(f"切分后仍存在超长块(len={len(text)}),请检查 chunk_size 配置!")
            for index, text in enumerate(spliter_chunks, start=1):
                final_chunks.append({
                    "content": text,
                    "title": f'{chunk["title"]}_{index}',  # title_1  _2  _3
                    "file_title": chunk["file_title"],
                    "part": index,
                    "parent_title": chunk["title"]
                })
        else:
            #5. 没有超过 -> 不需要二次切分 -> 补齐 part parent_title
            chunk['part'] = 0
            chunk['parent_title'] = chunk['title']
            final_chunks.append(chunk)
    #6. 循环结束后,返回结果即可(注意:return必须在for循环外!)
    return final_chunks


@step_log("step_4_merge_small_chunks")
def step_4_merge_small_chunks(chunks) -> List[Dict[str, str]]:
    """
       作用: 将低于最小阈值的相邻碎块合并,避免切分过碎导致语义不完整
       入参: chunks(step_3 输出,含 content/title/file_title/parent_title/part)
       出参: chunks(合并后的块列表)
       步骤:
         1. 准备结果容器 merged_chunks
         2. 从左到右扫描,用 accumulator 累积当前待合并块
         3. 同 parent_title 且累积块长度 < CHUNK_MIN_SIZE 且累积+下块长度 < CHUNK_MAX_SIZE -> 向后吸收下一块
         4. 否则落库 accumulator,并重置为当前块
         5. 循环结束后: 末块仍 < CHUNK_MIN_SIZE 且与前块同 parent_title -> 向前并入前块; 否则直接落库
         6. 日志并返回
    """
    #1. 准备结果容器
    merged_chunks = []
    accumulator = None  # 当前正在累积的合并块(dict)

    #2. 从左到右扫描
    for chunk in chunks:
        # 首个块 -> 直接作为合并起点
        if accumulator is None:
            accumulator = dict(chunk)
            continue
        #3. 判断是否需要向后合并(仅限同 parent_title)
        acc_len = len(accumulator["content"])
        if (accumulator["parent_title"] == chunk["parent_title"]
                and acc_len < CHUNK_MIN_SIZE
                and acc_len + len(chunk["content"]) < CHUNK_MAX_SIZE):
            # 向后合并: 主体取后块,内容按原顺序拼接(parent_title 前后恒等,无需赋值)
            accumulator["content"] = f'{accumulator["content"]}\n{chunk["content"]}'
            accumulator["title"] = chunk["title"]
            accumulator["part"] = chunk["part"]
        else:
            #4. 跨 parent_title / 已达最小阈值 / 再合并会超长 -> 落库并重置
            merged_chunks.append(accumulator)
            accumulator = dict(chunk)

    #5. 循环结束后处理最后一个累积块
    if accumulator is not None:
        # 末块仍低于最小阈值且与前块同 parent_title -> 向前并入前块(主体取前块)
        if (len(accumulator["content"]) < CHUNK_MIN_SIZE
                and merged_chunks
                and merged_chunks[-1]["parent_title"] == accumulator["parent_title"]):
            prev = merged_chunks[-1]
            prev["content"] = f'{prev["content"]}\n{accumulator["content"]}'
            # title/part 保持前块不变(parent_title 恒等)
        else:
            # 无同 parent_title 前块可并 -> 保留为短块(保证文档原意)
            merged_chunks.append(accumulator)

    #6. 日志并返回
    logger.info(f"合并小文本块完成,合并前块数:{len(chunks)},合并后块数:{len(merged_chunks)}")
    return merged_chunks


@step_log("step_5_backup_data")
def step_5_backup_data(chunks, md_path):
    """
    将数据存储到本地 文件夹名 / chunks.json
    """
    chunks_json_path_obj = Path(md_path).parent / "chunks.json"
    chunks_json_path_obj.write_text(json.dumps(
        chunks,
        ensure_ascii=False,  #中文直接原文存储
        indent=4    #json带有缩进4
    ), encoding="utf-8")



"""
chunk结构说明：
    "file_title": 去后缀的MD文件名
    "title": chunk标题（无标题时命名为【无标题】，精切后命名为原标题-部分数）
    "parent_title": 父标题（默认文件名，精切后为原标题）
    "part": 部分数（0代表没有精切，其余数字代表精切后的第几部分）
    "content": chunk内容
"""
@node_log("node_document_split")
def node_document_split(state: ImportGraphState) -> ImportGraphState:
    """
    节点: 文档切分 (node_document_split)
    为什么叫这个名字: 将长文档切分成小的 Chunks (切片) 以便检索。
    实现步骤:
    1. 进行任务的管理 running_task
    2. 数据校验和清洗 step_1_validate_clean
    3. 基于 Markdown 标题层级进行语义切分 step_2_split_by_title
    4. 对过长的块进行二次细分切割 step_3_data_refine_chunk
    5. 合并低于最小阈值的相邻碎块 step_4_merge_small_chunks
    6. 数据备份处理,写入 chunks.json step_5_backup_data
    7. 更新state属性 chunks
    8. 进行任务的管理 done_task
    """
     # 1. 记录进行状态
    add_running_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
     # 2. 数据校验和清洗 step_1_validate_clean
    md_content, file_title= step_1_validate_clean(state)
     # 3. 按照标题进行数据切割 step_2_split_by_title
     #[{content:标题的内容,title：标题,file_title：文件名},{},{}]
    chunks = step_2_split_by_title(md_content, file_title)
     # 4. 检查有没有超过指定的块,进行二次细分切割 step_3_data_refine_chunk
     #[{content, title, file_title, parent_title, part}, {}, {}]
    chunks = step_3_data_refine_chunk(chunks)
     # 5. 合并低于最小阈值的相邻碎块 step_4_merge_small_chunks
    chunks = step_4_merge_small_chunks(chunks)
     # 6. 数据备份处理,chunk.json  step_5_backup_data
    step_5_backup_data(chunks, state['md_path'])
     # 7. 修改state属性 chunks -> chunk切块列表
    state["chunks"] = chunks
     # 8. 进行任务的管理 done_task
    add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    return state



if __name__ == '__main__':
    """
    单元测试：联合node_md_img（图片处理节点）进行集成测试
    测试条件：1.已配置.env（MinIO/大模型环境） 2.存在测试MD文件 3.能导入node_md_img
    测试流程：先运行图片处理→再运行文档切分，验证端到端流程
    """

    """本地测试入口：单独运行该文件时，执行MD图片处理全流程测试"""
    from app.core.paths import PROJECT_ROOT
    from app.pipelines.import_pipeline.nodes.node_md_img import node_md_img

    logger.info(f"本地测试 - 项目根目录：{PROJECT_ROOT}")

    # 测试MD文件路径（需手动将测试文件放入对应目录）
    test_md_name = os.path.join(r"output\hak180产品安全手册", "hak180产品安全手册.md")
    test_md_path = os.path.join(PROJECT_ROOT, test_md_name)

    # 校验测试文件是否存在
    if not os.path.exists(test_md_path):
        logger.error(f"本地测试 - 测试文件不存在：{test_md_path}")
        logger.info("请检查文件路径，或手动将测试MD文件放入项目根目录的output目录下")
    else:
        # 构造测试状态对象，模拟流程入参
        test_state = {
            "md_path": test_md_path,
            "task_id": "test_task_123456",
            "md_content": "",
            "file_title": "hak180产品安全手册",
            "local_dir": os.path.join(PROJECT_ROOT, "output"),
        }
        logger.info("开始本地测试 - MD图片处理全流程")
        # 执行核心处理流程
        result_state = node_md_img(test_state)
        logger.info(f"本地测试完成 - 处理结果状态：{result_state}")
        logger.info("\n=== 开始执行文档切分节点集成测试 ===")

        logger.info(">> 开始运行当前节点：node_document_split（文档切分）")
        final_state = node_document_split(result_state)
        final_chunks = final_state.get("chunks", [])
        logger.info(f"✅ 测试成功：最终生成{len(final_chunks)}个有效Chunk{final_chunks}")