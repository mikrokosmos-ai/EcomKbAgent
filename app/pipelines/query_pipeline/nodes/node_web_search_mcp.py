import asyncio
import json
import sys
from agents.mcp import MCPServerStreamableHttp
from app.conf.bailian_mcp_config import mcp_config
from app.utils.task_utils import add_running_task, add_done_task
from app.core.logger import logger, node_log, step_log


DASHSCOPE_BASE_URL_STREAMBLE = mcp_config.mcp_base_url
DASHSCOPE_API_KEY = mcp_config.api_key


@step_log("step_1_data_validate")
def step_1_data_validate(state):
    rewritten_query = state['rewritten_query']
    if not rewritten_query:
        logger.error("rewritten_query不能为空!")
        raise ValueError("rewritten_query不能为空!")
    return rewritten_query


@step_log("node_web_search_mcp_async")
async def node_web_search_mcp_async(rewritten_query: str, count: int = 5):
    """
    使用openai的方式调用mcpserver提供的工具
    :param rewritten_query:
    :param count:
    :return:
    """
    # 1. 链接mcpserver服务
    mcp_server = MCPServerStreamableHttp(
        name="search_mcp",  # 随便写
        params={
            "url": DASHSCOPE_BASE_URL_STREAMBLE,
            "headers": {"Authorization": DASHSCOPE_API_KEY},
            "timeout": 300,
        },
        max_retry_attempts=3
    )

    try:
        # 2. 进行mcp_server链接
        await mcp_server.connect()
        # 3. 调用工具
        # https: // openai.github.io / openai - agents - python / ref / mcp / server /  # agents.mcp.server.MCPServer.call_tool
        tool_list = await mcp_server.list_tools()
        logger.info(f"工具列表:{tool_list}")
        mcp_result = await mcp_server.call_tool(
            tool_name="bailian_web_search",
            arguments={
                "query": rewritten_query,
                "count": count
            }
        )
        return mcp_result
    finally:
        # 4.释放本次链接资源
        await mcp_server.cleanup()


@node_log("node_web_search_mcp")
def node_web_search_mcp(state):
    """
    节点功能，调用外部搜索引擎补充信息
    :param state:
    :return:
    """
    # 1. 任务和认知
    add_running_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    # 2. 获取数据和校验
    rewritten_query = step_1_data_validate(state)
    # 3. mcp的调用流程封装成一个异步函数
    mcp_result = asyncio.run(node_web_search_mcp_async(rewritten_query, count=10))
    # 4. 结果解析
    # {
    #     "type": "tool_call",
    #     "content": [
    #        {
    #          text": "{\"pages\": [{\"title\": \"结果标题\", \"url\": \"结果链接\", \"snippet\": \"核心摘要\", \"source\": \"数据源\"}]}"
    #        }
    #     ]
    #  }
    #
    # mcp_result = {content:[{text:"{pages:[{x,x,x}]}"}]}
    text_dict = json.loads(mcp_result.content[0].text)
    pages = text_dict.get('pages', [])
    logger.info(f"联网搜索命中{len(pages)}条结果，明细：{pages}")
    # 记录任务结束
    add_done_task(state["session_id"], sys._getframe().f_code.co_name, state["is_stream"])
    return {"web_search_docs": pages}


from dotenv import load_dotenv

if __name__ == '__main__':
    load_dotenv()
    test_state = {
        "session_id": "xxxx",
        "is_stream": False,
        "rewritten_query": "HAK 180 在出厂默认状态下，若想在纸张上只把烫金膜转印到顶部 50 mm–170 mm 的局部区域，应在操作面板上如何设置"
    }

    # 调用 websearch_node 函数
    result_state = node_web_search_mcp(test_state)

    # 验证结果
    print("测试结果:")
    print(f"查询内容: {test_state.get('rewritten_query')}")
    print(f"查询内容: {result_state}")