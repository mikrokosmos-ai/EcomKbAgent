"""
    节点作用：调用minerU将PDF转Markdown
"""
import sys
import shutil
import time
from pathlib import Path
import httpx
from mineru import MinerU, ExtractResult
from typing import Tuple
from app.core.logger import logger, node_log, step_log
from app.pipelines.import_pipeline.state import ImportGraphState
from app.utils.task_utils import add_running_task, add_done_task
from app.conf.mineru_config import mineru_config

@step_log("step_1_validate_paths")
def step_1_validate_paths(state) -> Tuple[Path, Path]:
    """
       入参: state
      出参: pdf_path_obj [Path]  local_dir_obj [Path]
      步骤:
         1. state获取对应的地址
         2. 进行非空校验(pdf_path为空 -> 抛异常 | local_dir为空 -> 给予默认地址)
         3. 将两个参数转成Path (str -> Path )
         4. 判断pdf_path_obj是否有文件,local_dir_obj 是否存在文件夹
            没有文件 -> 抛出异常
            没有文件夹 -> 创建文件夹
         5. 返回两个路径地址
    """
    # 1. 获取state中定义的地址
    pdf_path = state['pdf_path']
    local_dir = state['local_dir']
    # 2. 做非空判断
    if not pdf_path:
        logger.error(f"pdf_path的值为空,无法读取文件,直接抛出异常!")
        raise ValueError("pdf_path的参数值为空,无法读取文件!")
    if not local_dir:
        local_dir = PROJECT_ROOT / "output"
        logger.info(f"step_1_validate_paths检查发现local_dir没有默认值,给默认值:{local_dir}!")
    # 3. 将地址转化成Path对象
    pdf_path_obj = Path(pdf_path)
    local_dir_obj = Path(local_dir)
    # 4. 判断是否真的存在
    if not pdf_path_obj.exists():
        logger.error(f"pdf_path:{pdf_path_obj},但是没有文件存在!")
        raise FileNotFoundError(f"pdf_path:{pdf_path_obj},但是没有文件存在!")
    if not local_dir_obj.exists():
        logger.warning(f"local_dir:{local_dir_obj}地址没有文件夹,我们需要主动创建!")
        # parents=True  可以创建多层结构文件夹
        # exist_ok=True 存在也不报错! 没有才会创建
        local_dir_obj.mkdir(parents=True, exist_ok=True)
    # 5. 返回两个路径地址
    return pdf_path_obj, local_dir_obj

@step_log("step_2_upload_and_poll")
def step_2_upload_and_poll(pdf_path_obj: Path) -> ExtractResult:
    """
    使用 minerU 官方 SDK 上传 PDF 并轮询解析,期间打印进度,返回解析结果对象

    入参: pdf_path_obj (Path) - 待解析的PDF文件路径对象
    出参: result (ExtractResult) - 解析结果(含 zip_url/markdown/已解压的 zip 字节)

    步骤:
      1. 校验minerU核心配置(api_key必填;base_url为空则走SDK默认地址)
      2. 初始化SDK客户端(with上下文管理器,退出时自动释放连接池)
      3. submit 提交解析任务(内部完成"申请上传地址 + 上传文件"),返回 batch_id
      4. get_batch 轮询解析状态,期间打印进度(已解析页/总页 + 百分比)
      5. 判定解析状态(failed 抛异常),返回 result
    """
    # 1. 校验minerU核心参数
    #    说明: base_url 在 SDK 有默认值 https://mineru.net/api/v4,为空时可省略;
    #    api_key(即 token)缺失则无法进入 Precision 精准解析模式,必须校验。
    if not mineru_config.api_key:
        logger.error("minerU配置错误,请检查minerU配置!")
        raise ValueError("minerU配置错误,请检查minerU配置!")

    # 2. 初始化SDK客户端
    with MinerU(
        token=mineru_config.api_key,
        base_url=mineru_config.base_url or None,
    ) as client:
        # 3. 提交解析任务(内部完成"申请上传地址 + 上传文件"),返回 batch_id
        #    model="vlm" 与原 model_version="vlm" 对齐
        #    重试说明：submit 阶段会向 mineru.net 发起网络请求，偶发断连
        #    (httpcore.RemoteProtocolError: Server disconnected without sending a response)，
        #    故对网络层异常(httpx.HTTPError 及其子类)加重试，避免任务直接失败。
        batch_id = None
        max_submit_retry = 3
        submit_retry_interval = 3  # 秒
        for attempt in range(1, max_submit_retry + 1):
            try:
                batch_id = client.submit(str(pdf_path_obj), model="vlm")
                break
            except httpx.HTTPError as e:
                logger.warning(f"提交解析任务出现网络异常(第{attempt}/{max_submit_retry}次),稍后重试!异常:{e}")
                if attempt >= max_submit_retry:
                    logger.error("提交解析任务重试耗尽,请检查网络或minerU服务!")
                    raise
                time.sleep(submit_retry_interval)

        logger.info(f"任务已提交,batch_id:{batch_id}")

        # 4. 轮询解析状态(带进度可视化 + 超时 + 网络异常重试)
        timeout = 600      # 轮询总超时(秒)
        interval_time = 3  # 轮询间隔(秒)
        start_time = time.time()
        result = None
        while True:
            # 4.1 判断是否超时
            if time.time() - start_time > timeout:
                logger.error("轮询超时,请检查minerU配置!")
                raise TimeoutError("轮询超时,请检查minerU配置!")

            # 4.2 轮询请求(鲁棒性: 网络层异常可重试,业务异常由SDK直接抛出)
            try:
                results = client.get_batch(batch_id)
            except httpx.HTTPError as e:
                # 覆盖连接失败/超时/5xx 等可修复网络异常,给 minerU 机会
                logger.warning(f"轮询请求出现网络异常,稍后重试!异常:{e}")
                time.sleep(interval_time)
                continue

            # 4.3 取首个解析结果(单文件提交,批次仅一项)
            if not results:
                logger.warning("尚未获取到任务结果,继续轮询!")
                time.sleep(interval_time)
                continue
            result = results[0]

            # 4.4 判定解析状态
            if result.state == "done":
                break
            if result.state == "failed":
                logger.error(f"minerU解析失败!错误码:{result.err_code},失败信息:{result.error}")
                raise RuntimeError(f"minerU解析失败!错误码:{result.err_code},失败信息:{result.error}")

            # 4.5 其他状态(pending/running/converting): 打印进度并继续等待
            progress_str = f"{result.progress}" if result.progress else "暂无进度信息"
            logger.info(f"解析正在进行中,状态:{result.state},进度:{progress_str}")
            time.sleep(interval_time)

    # 5. 返回解析结果(内含 zip_url + markdown + 已解压的 zip 字节)
    #    说明: 不再返回 zip_url 字符串,而是把完整 ExtractResult 交给 step_3,
    #    避免 step_3 再从 zip_url 二次下载。
    if not result.zip_url:
        logger.error("已经完成解析,但zip地址为空!")
        raise RuntimeError("已经完成解析,但zip地址为空!")
    return result


@step_log("step_3_save_and_extract")
def step_3_save_and_extract(result: ExtractResult, local_dir_obj: Path, stem: str) -> Path:
    """
    使用 minerU SDK 将已解析的结果包落地到本地,并确定最终 md 路径

    入参:
      result (ExtractResult) - step_2 轮询返回的解析结果(内含 zip 字节与 markdown)
      local_dir_path_obj (Path) - 输出根目录
      stem (str) - 文件名(无后缀)
    出参:
      md_path (Path) - 最终 markdown 文件路径 local_dir/stem/stem.md

    步骤:
      1. 确定目标目录 local_dir/stem
      2. 清空目标目录(避免脏数据)
      3. save_all 解压结果包(等价于原"下载zip -> 解压zip")
      4. 定位 full.md 并重命名为 stem.md
      5. 返回 md_path
    """
    # 1. 目标目录 local_dir/stem
    target_dir = local_dir_obj / f'{stem}'

    # 2. 清空旧目录(存在则整目录删除,由 save_all 自动重建)
    if target_dir.exists():
        shutil.rmtree(target_dir)

    # 3. 用 SDK 直接解压结果包到目标目录
    #    get_batch 在 state=done 时已内部下载并解析 zip,
    #    save_all 会把 zip 内容(full.md / images/ / content_list.json 等)整体解压,
    #    无需再从 zip_url 二次下载。
    result.save_all(str(target_dir))

    # 4. 定位 minerU 输出的 md 文件(full.md)并重命名为 stem.md
    full_md = target_dir / "full.md"
    if not full_md.exists():
        logger.error("解压结果中未找到 full.md,请检查 minerU 输出结构!")
        raise FileNotFoundError("解压结果中未找到 full.md,请检查 minerU 输出结构!")
    md_path = target_dir / f"{stem}.md"
    full_md.rename(md_path)

    # 5. 返回 md 路径
    return md_path

@node_log("node_pdf_to_md")
def node_pdf_to_md(state: ImportGraphState) -> ImportGraphState:
    """
        节点: PDF转Markdown (node_pdf_to_md)
        为什么叫这个名字: 核心任务是将 PDF 非结构化数据转换为 Markdown 结构化数据。
    """
     # 1. 日志+进行中的任务记录 add_running_task
    add_running_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
     # 2. step_1_validate_paths 校验pdf和输出地址
    pdf_path_obj,local_dir_obj = step_1_validate_paths(state)
     # 3. step_2_upload_and_poll minerU进行交互
     #参数:要解析pdf文件路径   返回值:解析结果 ExtractResult(含 zip_url/markdown/zip字节)
    result = step_2_upload_and_poll(pdf_path_obj)
    logger.info(f"minerU返回的zip地址:{result.zip_url}")
     # 4. step_3_save_and_extract 落地解析结果到本地
     #参数:1.解析结果 2.local_dir_obj解压的文件夹 3.文件名(无后缀)
    md_path = step_3_save_and_extract(result,local_dir_obj,pdf_path_obj.stem)
     # 5. 根据md地址读取对应md_content内容,并且更新state
    state['md_path'] = str(md_path)
    state['local_dir'] = str(local_dir_obj)
    md_content = md_path.read_text(encoding='utf-8')
    state['md_content'] = md_content
     # 6. 日志+完成的任务记录  add_done_task
    add_done_task(state['task_id'], sys._getframe().f_code.co_name, state.get("is_stream", False))
    return state


if __name__ == "__main__":
    import os
    from app.pipelines.import_pipeline.state import create_default_state
    from app.core.paths import PROJECT_ROOT

    # 单元测试：验证PDF转MD全流程
    logger.info("===== 开始node_pdf_to_md节点单元测试 =====")

    logger.info(f"测试获取根地址：{PROJECT_ROOT}")

    test_pdf_name = os.path.join("doc", "hak180产品安全手册.pdf")
    test_pdf_path = os.path.join(PROJECT_ROOT, test_pdf_name)

    # 构造测试状态
    test_state = create_default_state(
        task_id="test_pdf2md_task_001",
        pdf_path=test_pdf_path,
        local_dir=os.path.join(PROJECT_ROOT, "output")
    )

    node_pdf_to_md(test_state)

    logger.info("===== 结束node_pdf_to_md节点单元测试 =====")