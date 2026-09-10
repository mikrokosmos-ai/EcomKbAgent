import sys
from app.utils.task_utils import add_running_task, add_done_task, set_task_result
from app.utils.sse_utils import push_to_session, SSEEvent
from app.pipelines.query_pipeline.state import QueryGraphState
from app.core.logger import logger, node_log, step_log
from app.prompts.loader import load_prompt
from app.clients.llm_client import get_llm_client
from app.repositories.history_repo import save_chat_message
import re
from urllib.parse import urlparse

_IMAGE_BLOCK_MARKER = "【图片】"
MAX_CONTEXT_CHARS = 12000
# 证据区分块预算：本地 + 联网 + 历史 = MAX_CONTEXT_CHARS，三段互不挤占
LOCAL_EVIDENCE_BUDGET = 8000
WEB_EVIDENCE_BUDGET = 2500
HISTORY_BUDGET = MAX_CONTEXT_CHARS - LOCAL_EVIDENCE_BUDGET - WEB_EVIDENCE_BUDGET

# -----------------------------
# 图片域名白名单：只允许输出本库 MinIO 上的图片，阻断外链注入
# -----------------------------
try:
    from app.conf.minio_config import minio_config

    _IMAGE_HOST = (minio_config.endpoint or "").replace("http://", "").replace("https://", "").strip("/")
    _IMAGE_PATH_PREFIX = f"/{minio_config.bucket_name}/" if minio_config.bucket_name else "/"
except Exception as _e:
    # 配置缺失时 fail-closed：不信任任何图片 URL，避免退化成"全部放行"
    logger.warning(f"MinIO 配置加载失败，图片白名单为空（将拒绝所有图片 URL）: {_e}")
    _IMAGE_HOST = ""
    _IMAGE_PATH_PREFIX = "/"

# 零宽 / 双向控制字符：常被用于在资料中隐藏指令
_ZERO_WIDTH_RE = re.compile(r'[\u200b-\u200f\u202a-\u202e\u2060\ufeff]')
_URL_RE = re.compile(r'https?://[^\s，。；、（）【】「」]+')
_URL_TAIL_PUNCT_RE = re.compile(r'[)\]}\'">，。,;；】）＞]+$')


def _sanitize_evidence_text(text: str) -> str:
    """
    消毒：对进入 Prompt 的外部资料做无害化处理。
    1. 剥离零宽 / 双向控制字符（隐藏指令的常用载体）。
    2. 尖括号替换为全角，防止资料中出现 </本地知识库证据> 之类的闭合标签逃逸。
    """
    if not text:
        return ""
    text = _ZERO_WIDTH_RE.sub('', text)
    return text.replace('<', '＜').replace('>', '＞')


def _split_docs_by_type(reranked_docs):
    """
    分流：按 type 字段把重排结果拆成本地证据与联网证据。
    约定：type == "milvus" 为本地知识库；其余（web / 缺失 / 未知）一律归入
    最低信任的联网区 —— 默认值 fail-safe，宁可少信不可多信。
    """
    local_docs, web_docs = [], []
    for doc in reranked_docs or []:
        if doc.get("type") == "milvus":
            local_docs.append(doc)
        else:
            web_docs.append(doc)
    return local_docs, web_docs


def _build_evidence(docs, index_prefix: str, budget: int) -> str:
    """把一组文档拼成单个证据区字符串；超出预算即停止，返回已拼部分。"""
    blocks = []
    used = 0
    for i, doc in enumerate(docs, start=1):
        text = _sanitize_evidence_text((doc.get("text") or "").strip())
        if not text:
            continue
        meta_parts = [f"[{index_prefix}{i}]"]
        title = (doc.get("title") or "").strip()
        if title:
            meta_parts.append(f"[title={title}]")
        score = doc.get("score")
        if score is not None:
            try:
                meta_parts.append(f"[score={float(score):.4f}]")
            except (TypeError, ValueError):
                pass
        url = (doc.get("url") or "").strip()
        if url:
            meta_parts.append(f"[url={url}]")
        block = " ".join(meta_parts) + "\n" + text
        if used + len(block) > budget:
            break
        blocks.append(block)
        used += len(block) + 2
    return "\n\n".join(blocks)


def _build_history(history, budget: int) -> str:
    """
    历史对话独立预算，避免与证据区互相挤占。
    历史内容同样做消毒，防止多轮注入。
    """
    lines = []
    used = 0
    for msg in history or []:
        role = msg.get("role")
        text = msg.get("text")
        if role == "user" and text:
            line = f"用户: {_sanitize_evidence_text(text)}\n"
        elif role == "assistant" and text:
            line = f"助手: {_sanitize_evidence_text(text)}\n"
        else:
            continue
        if used + len(line) > budget:
            break
        lines.append(line)
        used += len(line)
    return "".join(lines) if lines else "无历史对话"


@step_log("step_1_check_answer")
def step_1_check_answer(state) -> bool:
    """
    阶段一：检查 state 中是否已有 answer。
    - 若已存在：按需推送流式 delta（用于 SSE），并返回 True
    - 若不存在：返回 False
    """
    answer = state.get("answer", None)
    is_stream = state.get("is_stream")
    if answer:
        if is_stream:
            logger.info("---Step 1: 发现已有答案，执行流式推送---")
            push_to_session(state["session_id"], SSEEvent.DELTA, {"delta": answer})
        else:
            set_task_result(state["session_id"], "answer", answer)
        return True
    else:
        return False


"""
目标结构
HAK 180 烫金机的操作面板位于机器正前方。开启电源后，您需要先设置温度，默认建议设置在 110℃ 左右。
具体的按键位置请参考下图：
【图片】
http://local-server/images/panel_view.jpg
http://local-server/images/button_detail.jpg
"""
@step_log("step_2_construct_prompt")
def step_2_construct_prompt(state: QueryGraphState) -> str:
    """
    第一阶段：构建 Prompt
    根据state中的问题、重新问题、历史对话、提问商品（item_names）、 重排内容 组织prompt
    """
    # 1. 获取相关信息
    original_query = state.get("original_query", "")
    rewritten_query = state.get("rewritten_query", "")
    # 优先使用重写后的问题
    question = rewritten_query if rewritten_query else original_query
    history = state.get("history", [])
    item_names = state.get("item_names", [])
    reranked_docs = state.get("reranked_docs") or []

    # 2 按来源分流：本地知识库（高信任）与联网结果（低信任）分别成区
    # 逻辑解释：
    # 1. reranked_docs 每条带 type 字段：milvus=本地知识库，web=联网结果。
    # 2. 两段证据各自独立预算（LOCAL_EVIDENCE_BUDGET / WEB_EVIDENCE_BUDGET），避免联网 snippet 与本地手册互相挤占。
    # 3. 未知 / 缺失 type 一律归入联网区（最低信任），默认 fail-safe。
    local_docs, web_docs = _split_docs_by_type(reranked_docs)
    local_evidence = _build_evidence(local_docs, "", LOCAL_EVIDENCE_BUDGET) \
        or "（本次未检索到本地知识库内容，请如实说明未找到，不要推测。）"
    web_evidence = _build_evidence(web_docs, "W", WEB_EVIDENCE_BUDGET) \
        or "（本次无联网补充资料。）"

    # 3. 格式化 History (历史对话)
    # 逻辑解释：
    # 1. 遍历历史对话记录 (history)，格式化为 "用户: ... \n 助手: ..." 的文本块。
    # 2. 历史区改用独立预算 HISTORY_BUDGET，不再与证据区共用计数器。
    # 3. 历史内容同样做消毒，防止多轮注入。
    history_str = _build_history(history, HISTORY_BUDGET)

    # 4. 格式化 Item Names (提问商品)
    item_names_str = ", ".join(item_names) if item_names else "无指定商品"

    # 5. 组装 Prompt
    prompt = load_prompt("answer_out",
                         local_evidence=local_evidence,
                         web_evidence=web_evidence,
                         history=history_str,
                         item_names=item_names_str,
                         question=question
                         )

    logger.info(f"组装后的提示词为：{prompt}")
    return prompt


@step_log("step_3_generate_response")
def step_3_generate_response(state: QueryGraphState, prompt: str) -> QueryGraphState:
    """
    第二阶段：生成回答
    调用llm生成答案，支持流式输出
    """
    logger.info("---Step 3: 开始生成回答 (LLM Generation)---")
    logger.debug(f"最终Prompt内容: {prompt}")

    # 获取 LLM 客户端
    # 注意：这里我们使用统一的 get_llm_client 获取实例
    llm = get_llm_client()

    # 判断是否需要流式输出
    # 通常 state 中会注入 stream_queue 用于 SSE 推送
    session_id = state.get("session_id")
    is_stream = state.get("is_stream")

    if is_stream:
        logger.info(f"模式: 流式输出 (Streaming), Session: {session_id}")
        final_text = ""
        try:
            # 使用 stream 方法进行流式生成
            for chunk in llm.stream(prompt):
                delta = getattr(chunk, "content", "") or ""
                if delta:
                    final_text += delta
                    # 将增量内容放入队列
                    push_to_session(session_id, SSEEvent.DELTA, {"delta": delta})

            logger.info(f"流式输出完成，总长度: {len(final_text)}")

        except Exception as e:
            logger.error(f"流式生成出错: {e}", exc_info=True)
            # 发生错误时，尝试推送到前端
            push_to_session(session_id, SSEEvent.ERROR, {"error": str(e)})

        state["answer"] = final_text
    else:
        # 非流式直接调用
        logger.info(f"模式: 非流式输出 (Blocking), Session: {session_id}")
        try:
            response = llm.invoke(prompt)
            content = response.content
            state["answer"] = content
            set_task_result(session_id, "answer", content)
            logger.info(f"生成回答完成，长度: {len(content)}")
        except Exception as e:
            logger.error(f"生成回答出错: {e}", exc_info=True)
            state["answer"] = "抱歉，生成回答时出现错误。"

    return state


def _extract_images_from_docs(docs):
    """
    辅助方法：从文档列表中提取图片URL

    核心逻辑：
    1. 遍历所有相关文档（包括本地知识库切片和联网搜索结果）。
    2. 策略一：直接检查文档的 'url' 字段（常见于联网搜索结果）。
       - 验证后缀名是否为图片格式 (.jpg, .png 等)。
    3. 策略二：使用正则表达式扫描文档 'text' 正文内容（常见于本地 Markdown 文档）。
       - 匹配 Markdown 图片语法: ![alt text](image_url)。
    4. 对提取到的 URL 进行去重处理，返回唯一图片列表。

    :param docs: 文档列表，每个文档为字典格式
    :return: 图片 URL 字符串列表
    """
    images = []
    seen = set()  # 用于去重，避免同一张图片重复出现
    if not docs:
        return []

    # 注意：图片 alt 文本常含换行（图片摘要由 LLM 生成，是多行内容），
    # 必须启用 DOTALL，否则 alt 跨行的图片会被整段漏掉。
    md_img_pattern = re.compile(r'!\[.*?\]\((.*?)\)', re.DOTALL)
    logger.info(f"开始提取图片，待处理文档数: {len(docs)}")

    for i, doc in enumerate(docs):
        # 1. 优先检查 url 字段 (主要针对 Web Search 结果)
        url = (doc.get("url") or "").strip()
        if url:
            # 简单后缀判断：确保是静态图片资源
            if url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg')):
                if url not in seen:
                    logger.debug(f"文档[{i}] 发现图片 URL (字段): {url}")
                    seen.add(url)
                    images.append(url)

        # 2. 检查 text 字段中的 Markdown 图片 (主要针对 Local Chunk)
        text = (doc.get("text") or "").strip()
        if text:
            # findall 机制解释：
            # 正则表达式 r'!\[.*?\]\((.*?)\)' 中包含一个捕获组 (.*?)
            # 当存在捕获组时，findall 只返回括号内匹配到的内容（即 URL），而不是整个 ![...](...) 字符串
            # 示例：
            # 输入 text: "参考图片 ![面板图](http://img.com/1.jpg) 如下"
            # 返回 matches: ['http://img.com/1.jpg']
            matches = md_img_pattern.findall(text)
            for img_url in matches:
                img_url = img_url.strip()
                if img_url and img_url not in seen:
                    logger.debug(f"文档[{i}] 正文发现 Markdown 图片: {img_url}")
                    seen.add(img_url)
                    images.append(img_url)

    logger.info(f"图片提取完成，共找到 {len(images)} 张唯一图片: {images}")
    return images


def _extract_images_from_answer(answer: str) -> list:
    """
    从 LLM 生成的答案中解析【图片】区块里的图片 URL。

    与前端 findLastImageMarkerIndex 保持一致：定位答案中最后一个
    「【图片】」/「[图片]」标记，提取其后的 URL，过滤出图片后缀。

    核心目的：图片展示以 LLM 显式引用为准 —— 答案里没有【图片】区块时，
    返回空列表，前端不展示任何图片。

    :param answer: LLM 生成的答案文本
    :return: 图片 URL 列表（无区块则为空列表）
    """
    if not answer:
        return []
    matches = list(re.finditer(r'【\s*图片\s*】|\[\s*图片\s*\]', answer))
    if not matches:
        return []
    after = answer[matches[-1].end():].strip()
    images = []
    seen = set()
    for line in after.splitlines():
        line = line.strip()
        if not line:
            continue
        # 每行一个 URL（约定）；字符集排除中文标点，避免吞入后续文字
        for raw_url in re.findall(r'https?://[^\s，。；、（）【】「」]+', line):
            # 去除 URL 尾部的标点符号（中英文逗号、括号等）作为双保险
            url = re.sub(r'[)\]}\'">，。,;；】）＞]+$', '', raw_url).strip()
            if not url or url in seen:
                continue
            path = url.split('?')[0].split('#')[0].lower()
            if path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg')):
                seen.add(url)
                images.append(url)
    return images


def _is_trusted_image_url(url: str) -> bool:
    """
    图片域名白名单校验：必须是本库 MinIO（endpoint + bucket）下的地址。
    配置缺失时 _IMAGE_HOST 为空，本函数恒返回 False（fail-closed）。
    """
    if not url:
        return False
    u = str(url).strip()
    if not u.lower().startswith(("http://", "https://")):
        return False
    try:
        parsed = urlparse(u)
    except Exception:
        return False
    if not _IMAGE_HOST or parsed.netloc.lower() != _IMAGE_HOST.lower():
        return False
    return parsed.path.startswith(_IMAGE_PATH_PREFIX)


def _strip_untrusted_links(answer: str) -> str:
    """
    输出侧清洗，针对"答案正文里的普通外链"这一 prompt 够不到的缺口：
    1. 正文（【图片】区块之前）：非白名单 URL 替换为「【已移除外部链接】」；
       白名单（本库 MinIO）URL 原样保留。
    2. 【图片】区块内：整行剔除含非白名单 URL 的行，避免前端渲染外链图片。
    """
    if not answer:
        return answer

    markers = list(re.finditer(r'【\s*图片\s*】|\[\s*图片\s*\]', answer))
    if markers:
        body = answer[:markers[-1].start()]
        tail = answer[markers[-1].start():]
    else:
        body, tail = answer, ""

    def _mask(match):
        url = _URL_TAIL_PUNCT_RE.sub('', match.group(0)).strip()
        return url if _is_trusted_image_url(url) else "【已移除外部链接】"

    body = _URL_RE.sub(_mask, body)

    if tail:
        kept_lines = []
        for line in tail.splitlines():
            urls = [_URL_TAIL_PUNCT_RE.sub('', u).strip() for u in _URL_RE.findall(line)]
            if urls and not all(_is_trusted_image_url(u) for u in urls):
                continue
            kept_lines.append(line)
        tail = "\n".join(kept_lines)
    return body + tail


@step_log("step_4_write_history")
def step_4_write_history(state: QueryGraphState, image_urls=None) -> QueryGraphState:
    """
    阶段四：把本轮答案写入 MongoDB history。
    利用 app/repositories/history_repo.py 中的 save_chat_message 方法。
    """
    session_id = state.get("session_id", "default")
    answer = (state.get("answer") or "").strip()
    item_names = state.get("item_names") or []

    try:
        if answer:
            save_chat_message(
                session_id=session_id,
                role="assistant",
                text=answer,
                rewritten_query="",
                item_names=item_names,
                image_urls=image_urls,
                message_id=None
            )
    except Exception as e:
        # 写历史失败不应影响主链路
        logger.error(f"写入Mongo历史记录失败: {e}")

    return state


@node_log("node_answer_output")
def node_answer_output(state: QueryGraphState) -> QueryGraphState:
    """
    1 判断state 中的answer是否已经存在，如果存在直接输出answer中的答案，注意判断是否需要流式输出需要则流式输出
    2 根据state中的问题、重新问题、历史对话、提问商品（item_names）、 重排内容 组织prompt 并调用llm 生成答案
    3 阶段三：调用大模型输出答案 注意判断是否需要流式输出需要则流式输出
    4 把答案写入到mongodb的history中 利用app/repositories/history_repo.py中的save_chat_message方法
    5 做最后一次push操作（主要是为了触发前端图片渲染)
       {
          "answer": "HAK 180 烫金机的操作面板位于...（大模型生成的纯文本）...",
          "status": "completed",
          "image_urls": [
              "http://local-server/images/panel_view.jpg",
              "http://local-server/images/button_detail.jpg"
          ]
        }
    """
    add_running_task(state['session_id'], sys._getframe().f_code.co_name, state.get("is_stream"))
    # 阶段一：检查answer是否存在,如果存在直接输出answer中的答案
    answer_exists = step_1_check_answer(state)
    # 阶段二  如果没有answer则 构建 Prompt
    if not answer_exists:
        prompt = step_2_construct_prompt(state)
        state["prompt"] = prompt

        # 阶段三：  如果没有answer则 调用大模型输出答案
        step_3_generate_response(state, prompt)

    # 提取图片URL（用于历史记录和前端展示）
    # 先对答案做输出侧清洗（正文非白名单外链替换、【图片】区非白名单 URL 整行剔除）
    raw_answer = (state.get("answer") or "").strip()
    safe_answer = _strip_untrusted_links(raw_answer)
    if safe_answer != raw_answer:
        logger.warning("答案中检出非白名单外链，已做清洗处理")
        state["answer"] = safe_answer
        # 非流式路径下 step_3 已把原始答案写入 task_result，这里同步为清洗后的版本，
        # 否则轮询结果的调用方拿到的仍是未经清洗的答案。
        if not state.get("is_stream"):
            set_task_result(state["session_id"], "answer", safe_answer)
    answer_text = safe_answer

    # 候选图片只取本地知识库证据（type=milvus），并叠加域名白名单。
    local_docs, _ = _split_docs_by_type(state.get("reranked_docs") or [])
    candidate_images = [u for u in _extract_images_from_docs(local_docs)
                        if _is_trusted_image_url(u)]
    answer_images = _extract_images_from_answer(answer_text)

    # 与检索到的候选图片做交集：过滤 LLM 可能幻觉编造的 URL，
    # 并统一回填为候选集中规范的那条 URL（容错空格/大小写差异）。
    candidate_norm = {re.sub(r'\s+', '', u).lower(): u for u in candidate_images}
    image_urls = []
    for u in answer_images:
        key = re.sub(r'\s+', '', u).lower()
        if key in candidate_norm:
            image_urls.append(candidate_norm[key])

    # 回写 state，供 query_router 兜底 FINAL 事件读取，保证流式/非流式一致
    state["image_urls"] = image_urls

    # 阶段四：把答案写入到mongodb的history中
    if state.get("answer"):
        logger.info("---写入MongoDB历史记录---")
        step_4_write_history(state, image_urls=image_urls)
    add_done_task(state['session_id'], sys._getframe().f_code.co_name, state.get("is_stream"))

    # 阶段五: 流式输出结束，发送 final 事件 [最后兜底，确保图片都能争取渲染和结束]
    logger.info(f"---发送 final 事件---图片为：{image_urls}")
    if state.get("is_stream"):
        push_to_session(
            state['session_id'],
            SSEEvent.FINAL,
            {
                "answer": state["answer"],
                "status": "completed",
                "image_urls": image_urls  # 发送图片URL给前端
            }
        )
    return state



if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(">>> 启动 node_answer_output 本地测试")
    print("=" * 50)

    # 1. 构造模拟数据
    # 模拟重排序后的文档列表 (reranked_docs)
    # 包含：本地文档（带Markdown图片）、联网结果（带URL字段）、纯文本文档
    # 注意：来源标识字段是 type（milvus=本地知识库 / web=联网结果）。
    # 重排节点不会产出 source / chunk_id（原 mock 用的 source 恒为空），
    # mock 数据需与真实结构一致，否则会全部落到最低信任的联网区。
    mock_reranked_docs = [
        {
            "type": "milvus",
            "title": "HAK 180 烫金机操作手册_v2.pdf",
            "score": 0.95,
            "text": """
            HAK 180 烫金机的操作面板位于机器正前方。
            开启电源后，您需要先设置温度，默认建议设置在 110℃ 左右。
            具体的操作面板布局请参考下图：
            ![操作面板布局图](http://127.0.0.1:9000/knowledge-base-files/upload-images/panel_view.jpg)

            如果是进行局部烫金，请调节侧面的旋钮。
            ![侧面旋钮细节](http://127.0.0.1:9000/knowledge-base-files/upload-images/knob_detail.png)
            """
        },
        {
            "type": "web",
            "title": "HAK 180 常见故障排除 - 官网",
            "score": 0.88,
            "url": "http://example.com/hak180_troubleshooting.jpeg",  # 联网结果的图片，按设计不参与图片候选
            "text": "如果机器无法加热，请检查保险丝是否熔断..."
        },
        {
            "type": "milvus",
            "title": "安全注意事项",
            "score": 0.82,
            "text": "操作时请务必佩戴隔热手套，避免高温烫伤。"
        }
    ]

    # 模拟历史记录
    mock_history = [
        {"role": "user", "text": "你好，这款机器怎么用？"},
        {"role": "assistant", "text": "您好！请问您具体指的是哪一款机器？"},
        {"role": "user", "text": "HAK 180 烫金机"}
    ]

    # 模拟输入状态
    mock_state = {
        "session_id": "test_answer_session_001",
        "original_query": "HAK 180 烫金机怎么操作？",
        "rewritten_query": "HAK 180 烫金机的具体操作步骤和面板设置方法",
        "item_names": ["HAK 180 烫金机"],
        "history": mock_history,
        "reranked_docs": mock_reranked_docs,
        "is_stream": False,  # 测试非流式
        # "is_stream": True, # 若要测试流式，需确保 SSE 环境或 mock 相关函数
        "answer": None  # 初始无答案
    }

    try:
        # 运行节点
        result = node_answer_output(mock_state)

        print("\n" + "=" * 50)
        print(">>> 测试结果摘要:")

        # 1. 验证 Prompt 构建
        if "prompt" in result:
            print(f"[PASS] Prompt 构建成功 (长度: {len(result['prompt'])})")
            # print(f"Prompt 预览:\n{result['prompt'][:200]}...")
        else:
            print("[FAIL] Prompt 未构建")

        # 2. 验证答案生成
        answer = result.get("answer")
        if answer and len(answer) > 10:
            print(f"[PASS] 答案生成成功 (长度: {len(answer)})")
            print(f"答案预览: {answer[:50]}...")
        else:
            print(f"[WARN] 答案生成可能异常 (Content: {answer})")

        # 3. 验证图片提取
        # 期望：只有 type=milvus 且命中 MinIO 白名单（host + bucket 路径）的图片进入候选，
        # 即下面 2 张；联网结果的图片按设计被排除，用于阻断外链注入。
        print(f"\n[INFO] 最终 image_urls = {result.get('image_urls')}")
        print("[INFO] 白名单内本地图片（应出现在候选中）:")
        print(" - http://127.0.0.1:9000/knowledge-base-files/upload-images/panel_view.jpg")
        print(" - http://127.0.0.1:9000/knowledge-base-files/upload-images/knob_detail.png")
        print("[INFO] 联网图片（不应出现在候选中）:")
        print(" - http://example.com/hak180_troubleshooting.jpeg")

        print("=" * 50)

    except Exception as e:
        logger.exception(f"测试运行期间发生未捕获异常: {e}")