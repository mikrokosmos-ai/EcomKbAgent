"""
    就是将md中的图片进行单独处理,图片转成对应的语义文本,方便后续进行切片搜索
"""
import sys
import os
import re
import base64
from pathlib import Path
from typing import Dict, List, Tuple
import mimetypes
# MinIO相关依赖
from minio.deleteobjects import DeleteObject
# 【核心改造1：移除原生OpenAI，导入LangChain工具类和多模态消息模块】
from app.clients.minio_client import get_minio_client
from app.pipelines.import_pipeline.state import ImportGraphState
from app.utils.task_utils import add_running_task, add_done_task
from langchain_core.output_parsers import StrOutputParser
# LLM客户端工具类（核心复用，替换原生OpenAI调用）
from app.clients.llm_client import get_llm_client
# LangChain多模态依赖（消息构造+异常捕获）
from langchain.messages import HumanMessage
# 项目配置
from app.conf.minio_config import minio_config
from app.conf.lm_config import lm_config
# 导入链路配置：图片摘要限流参数（默认值等于改造前 apply_api_rate_limit 的默认值 9 次 / 60 秒）
from app.conf.import_pipeline_config import import_pipeline_config
# 项目日志工具（统一使用）
from app.core.logger import logger, node_log, step_log
# api访问限速工具
from app.core.rate_limit import apply_api_rate_limit
# 提示词加载工具
from app.prompts.loader import load_prompt

# MinIO支持的图片格式集合（小写后缀，统一匹配标准）
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

def is_supported_image(filename: str) -> bool:
    """
    判断文件是否为MinIO支持的图片格式（后缀不区分大小写）
    :param filename: 文件名（含后缀）
    :return: 支持返回True，否则False
    """
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS

@step_log("step_1_get_content")
def step_1_get_content(state) -> Tuple[str, Path, Path]:
    """
        入参: state [md_content md_path]
       出参: md_content , md_path_obj:Path , images_dir_obj : Object
       步骤:
            1. 获取md_content 和 md_path
            2. 非空校验 (为空就异常 ValueError)
            3. md_path 转成 md_path_obj Path
            4. md_path_obj 获取 images所在的文件夹  .parent / images
    """
    # 1.获取基本信息
    md_content = state["md_content"]
    md_path = state["md_path"]
    # 2. 非空校验
    if not md_path:
        logger.error(f"md_path核心参数为空,无法继续!!")
        raise ValueError("md_path核心参数为空,无法继续!!")
    # 3. md_path转成Path对象
    md_path_obj = Path(md_path)

    if not md_content:
        logger.warning("md_content为空,根据地址读取!")
        state["md_content"] = md_path_obj.read_text(encoding="utf-8")
    # 4. 图片文件夹
    images_path_ojb = md_path_obj.parent / "images"
    return state["md_content"], md_path_obj, images_path_ojb


@step_log("step_2_scan_images")
def step_2_scan_images(md_content:str, images_path_obj:Path) -> List[Tuple[str, str, Tuple[str, str]]]:
    """
    作用: 找到图片的本身信息和图片的上下文信息
    入参: md_content ,  images_dir_obj
    出参: [("图片名.xx","图片地址",(上文 -> 100,下文 -> 100))]
    步骤:
        1. 获取图片文件夹中所有图片对象
        2. 循环遍历图片对象
        3. 定义对应的正则规则 ![](图片名)
        4. md中进行正在匹配
        5. 获取图片在 MD 中的位置
        6. md中截取上文和下文 md_content [ star-100 : star]   [end , end+100]
        7. 拼接结果内容 (对象.name , str(对象) , (上文,下文))
    """
    #1. 准备一个列表接收整体结果
    targets = []
    #2. 循环遍历
    for image_file in images_path_obj.iterdir():
        # image_file 每个图片的Path对象
        image_name = image_file.name
        if not is_supported_image(image_name):
            logger.warning(f"{image_name}不是图片,无需处理,跳过本次!!")
            continue
        #3. 正则匹配 MD 中的图片语法：![...](...图片名...),   .*? 非贪婪匹配
        # re.escape 处理文件名中带特殊字符（如括号、点）导致正则爆炸的问题
        rep = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_name) + r".*?\)")
        #4. md中进行正在匹配 Match = re.search(md)
        items = list(rep.finditer(md_content))
        if not items:
            logger.warning(f"{image_name}没有在md中使用,跳过本次处理!")
            continue
        #5. 获取图片在 MD 中的位置
        start, end = items[0].span()  #span获取匹配对象的起始和终止的位置
        #6. 获取上下文 100
        pre_content = md_content[max(start - 100, 0):start]
        pos_content = md_content[end:min(end + 100, len(md_content))]
        content = (pre_content,pos_content)
        #7. 拼接结果内容(对象.name, str(对象), (上文, 下文))
        targets.append((image_name, str(image_file), content))
    return targets


@step_log("step_3_image_summary")
def step_3_image_summary(targets, stem) -> Dict[str, str]:
    """
        作用: 使用视觉模型识别图片描述内容
       入参: [("图片名.xx","图片地址",(上文 -> 100,下文 -> 100))]   md_path_obj.stem (图片所在的文件夹的名字)
       出参: dict {图片名 : 图片的总结和描述}
       步骤:
             1. 先准备放结果的字典
             2. 获取模型客户端对象
             3. 循环总结每份图片
             4. 封装提示词
             5. 获取返回结果 装到 dict中
             6. 返回结果
    """
    # 1. 先准备放结果的字典
    summaries = {}
    # 2. 获取模型法对象
    vm_model = get_llm_client(lm_config.lv_model)
    chain = vm_model | StrOutputParser()
    # 3. 循环总结每份图片
    for image_name, image_path, context in targets:
        # 4. 构建提示词
        # 访问限制（参数来源：app/conf/import_pipeline_config.py）
        apply_api_rate_limit(
            max_requests=import_pipeline_config.image_summary_rate_max_requests,
            window_seconds=import_pipeline_config.image_summary_rate_window_seconds,
        )
        prompt = load_prompt("image_summary", root_folder=stem,image_content=context)
        # base64.b64encode(字节) 普通字节转成base64的字节 .decode(encoding="utf-8") 转成字符串
        image_path_obj = Path(image_path)
        image_data = base64.b64encode(image_path_obj.read_bytes()).decode(encoding="utf-8")
        message = HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {
                        # 1. 图片地址 必须公网地址 http://xxxx [图片上传到minio]
                        # 2. base64的字符串  字节 -> 字符 -> 服务器 -> 字符 -> 字节
                        "url": f"data:{mimetypes.guess_type(image_name)[0]};base64,{image_data}"
                    },
                },
                # 本次图片的上下文文本描述
                {"type": "text", "text": f"{prompt}"},
            ]
        )
        #5.获取返回结果装到dict中
        result = chain.invoke([message])
        summaries[image_name] = result
    #6.返回结果
    return summaries


@step_log("step_4_upload_and_replace")
def step_4_upload_and_replace(summaries, targets, md_content, stem) -> str:
    """
    作用: 将图片传递到minio,拼接网络地址,联合混合模型返回的图片描述,一起替换md_content内容
    入参: md_content  [("图片名.xx","图片地址",(上文 -> 100,下文 -> 100))] dict {图片名 : 图片的总结和描述}  md_path_obj.stem
    出参: md_content 替换后的  ![](本地地址) -> ![summary](网络地址)
    步骤:
        1.获取minio的客户端对象 minio_client
        2.删除原文件名对应的minio对象
        3.循环"图片地址"地址向minio服务器传递文件,并且拼接(端点/桶名/对象名)和记录地址 {图片名:图片地址}
        4. {图片名:图片地址}   {图片名 : 图片的总结和描述} -> 合并到一起 -> {图片名 : (图片描述和总结,图片地址)}
        5. md_content内容替换,循环处理和替换即可 正则 |  rep.sub("要替换进入的内容",md_content)
        6. 最终返回md_content
    """
    #1.获取minio的客户端对象 minio_client
    minio_client = get_minio_client()
    #2.删除原文件名对应的minio对象(先查询,再删除!)
    object_list = minio_client.list_objects(
        bucket_name=minio_config.bucket_name,
        # 前缀 ([1:]) 不能使用 /开头 必须使用 /结尾
        prefix=f"{minio_config.minio_img_dir[1:]}/{stem}/",
        recursive=True
    )
    delete_object_list = [DeleteObject(obj.object_name) for obj in object_list]
    # 底层是懒执行! 必须调用结果! 否则不执行!!!
    errors = minio_client.remove_objects(
        bucket_name = minio_config.bucket_name,
        delete_object_list = delete_object_list
    )
    for error in errors:
        logger.warning(f"删除失败,失败原因:{error}")
    logger.debug("=============删除成功======================")

    #3.循环"图片地址"地址向minio服务器传递文件,并且拼接(端点/桶名/对象名)和记录地址 {图片名:图片地址}
    images_url = {}
    for image_name, image_path, _ in targets:
        try:
            minio_client.fput_object(
                bucket_name=minio_config.bucket_name,
                object_name=f"{minio_config.minio_img_dir}/{stem}/{image_name}",
                file_path=image_path,
                content_type=mimetypes.guess_type(image_name)[0]
            )
            # 拼接图片的网络地址  端点 + 桶 + 对象名
            image_minio_url = f"http://{minio_config.endpoint}/{minio_config.bucket_name}{minio_config.minio_img_dir}/{stem}/{image_name}"
            logger.debug(f"图片:{image_name}上传成功!回显地址:{image_minio_url}")
            # 存储图片和对应网络地址对
            images_url[image_name] = image_minio_url
        except Exception as e:
            logger.warning(f"异常：{e}导致本次图片上传失败:{image_name},跳过继续上传下一张!")
            continue
    #4.把targets{图片名:图片地址}和summaries：{图片名 : 图片的总结和描述}合并到一起 -> {图片名 : (图片地址,图片描述和总结)}
    image_infos = {}
    if not images_url:
        logger.warning("图片上传全部失败!")
        return md_content

    for image_name, image_url in images_url.items():
        image_infos[image_name] = (image_url, summaries[image_name])
    #5.md_content内容替换,循环处理和替换即可 正则 |  rep.sub("要替换进入的内容",md_content)
    for image_name, (image_url, image_summary) in image_infos.items():
        rep = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_name) + r".*?\)")
        # 使用lambda表达式处理, 正则就不会处理, 只会使用原生的正则返回值!
        md_content = rep.sub(lambda _: f"![{image_summary}]({image_url})", md_content)
    #6.最终返回md_content
    return md_content


@step_log("step_4_backup_md")
def step_5_backup_md(new_md_content, md_path_obj) -> str:
    """
    将新的md_content内容写入到本地磁盘! xx.md xx_new.md
    :param new_md_content: 新内容
    :param md_path_obj: 老地址
    :return: 新md的地址 str
    """
    # with_name -> 磁盘没关系,获取一个新的path / rename 重命名 修改磁盘
    new_md_path_obj = md_path_obj.with_name(f"{md_path_obj.stem}_new.md")
    # 备份
    new_md_path_obj.write_text(new_md_content, encoding="utf-8")
    return str(new_md_path_obj)


@node_log("node_md_img")
def node_md_img(state: ImportGraphState) -> ImportGraphState:
    """
        节点: 图片处理 (node_md_img)
        实现步骤:
            1. 进行任务的管理 running_task
            2. 进行参数校验和获取材料 step_1_get_content
            3. 扫描图片的上下文 step_2_scan_images
            4. 调用视觉模型,传入图片的对应的上下文,获取图的文本内容 step_3_image_summary
            5. 将图片文件传入到minio服务器,并且进行md中的图片替换(描述 网络地址) step_4_upload_images_replace
            6. 将新的md内容进行备份处理 step_5_backup_md
            7. 更新state信息 md_path md_content
            8. 进行任务的管理 done_task
    """
     # 1. 记录进行状态
    add_running_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
     # 2. 准备和校验
    md_content,md_path_obj, images_dir_obj = step_1_get_content(state)
     # 提前结束识别
    if not images_dir_obj.exists() or len(list(images_dir_obj.iterdir())) == 0:
        logger.warning(f"图片文件夹为空或者没有图片,无需后续处理!")
        return state
     # 3. 扫描图片的上下文 step_2_scan_images
     #响应： [(图片名,图片地址,(上文,下文))]
    targets = step_2_scan_images(md_content,images_dir_obj)
    logger.info(f"已经获取上下文信息:{targets}")
     # 4. 调用模型识别图片的描述文本
    # {图片名 : 描述 } ....
    summaries = step_3_image_summary(targets, md_path_obj.stem)
    logger.info(f"图片摘要生成完成,共{len(summaries)}条:{summaries}")
    # 5. 上传图片,并且替换md_content内容
    new_md_content =  step_4_upload_and_replace(summaries, targets,md_content, md_path_obj.stem)
    # 6. new_md_content新的备份
    new_md_file_path = step_5_backup_md(new_md_content, md_path_obj)
    # 7. 更新state数据
    state['md_content'] = new_md_content
    state['md_path'] = new_md_file_path
    #8.进行任务的管理done_task
    add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    return state


if __name__ == "__main__":
    """本地测试入口：单独运行该文件时，执行MD图片处理全流程测试"""
    from app.core.paths import PROJECT_ROOT
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
            "md_content": ""
        }
        logger.info("开始本地测试 - MD图片处理全流程")
        # 执行核心处理流程
        result_state = node_md_img(test_state)
        logger.info(f"本地测试完成 - 处理结果状态：{result_state}")

