"""
中间件与外部服务连通性自检脚本

作用：
    在启动服务前，一次性探测全部外部依赖是否可用，逐项打印 [OK]/[FAIL] 与耗时，
    把"环境没配好"与"业务逻辑有问题"这两类问题在动手排查前就区分开。

用法（**必须在项目根目录下用 -m 方式运行**）：
    python -m scripts.check_connections                  # 基础项：Milvus / MongoDB / MinIO / LLM
    python -m scripts.check_connections --skip-llm       # 跳过 LLM（不想消耗额度时）
    python -m scripts.check_connections --skip-mcp       # 跳过 MCP 联网工具探测
    python -m scripts.check_connections --with-models    # 追加本地模型加载检测（BGE-M3 / Reranker，较慢）

退出码：
    0 = 全部通过；1 = 存在失败项；2 = 运行方式不正确

耗时说明：
    探测**沿用应用自身的客户端配置**（而非另建短超时连接），以保证"自检通过 = 应用可用"。
    因此当 MongoDB / MinIO 未启动时，本脚本会在库默认超时（约 30 秒 / 约 18 秒）后才报 FAIL，
    属预期现象；基础设施正常时各项均为毫秒级。

"""
import argparse
import asyncio
import time
from typing import Callable, List, Optional, Tuple

# 运行方式守卫：必须在导入 app.* 之前判断，避免直接运行时报出令人困惑的 ModuleNotFoundError
if __package__ in (None, ""):
    print("[提示] 本脚本需以模块方式运行，请在项目根目录执行：")
    print("       python -m scripts.check_connections")
    raise SystemExit(2)

# ==================== 输出辅助 ====================
_PASS, _FAIL = "OK", "FAIL"


def _run_check(name: str, fn: Callable[[], Optional[str]]) -> bool:
    """
    执行单项检查并打印结果

    :param name: 检查项名称（左侧列）
    :param fn: 无参可调用对象；正常返回一段补充说明（可为 None），异常即视为失败
    :return: 是否通过
    """
    start = time.perf_counter()
    try:
        detail = fn()
        cost_ms = (time.perf_counter() - start) * 1000
        print(f"[{_PASS}] {name:<26} {cost_ms:>8.0f} ms  {detail or ''}")
        return True
    except Exception as e:
        cost_ms = (time.perf_counter() - start) * 1000
        print(f"[{_FAIL}] {name:<26} {cost_ms:>8.0f} ms  {type(e).__name__}: {e}")
        return False


def _print_header(title: str, rows: List[Tuple[str, str]]) -> None:
    """打印分组标题与"将要探测的目标"（只输出地址/名称，不输出任何密钥）"""
    print(f"\n--- {title} ---")
    for k, v in rows:
        print(f"       {k:<14} = {v}")


# ==================== 各依赖项检查 ====================
def check_milvus() -> Optional[str]:
    """Milvus：建连 + 列出集合 + 报告两个业务集合是否已存在"""
    from app.clients.milvus_client import get_milvus_client
    from app.conf.milvus_config import milvus_config

    client = get_milvus_client()
    collections = client.list_collections()
    chunks_ok = client.has_collection(milvus_config.chunks_collection)
    item_ok = client.has_collection(milvus_config.item_name_collection)
    return (
        f"集合总数={len(collections)} | "
        f"{milvus_config.chunks_collection}={'已建' if chunks_ok else '未建'} | "
        f"{milvus_config.item_name_collection}={'已建' if item_ok else '未建'}"
    )


def check_mongo() -> Optional[str]:
    """MongoDB：ping + 报告库名与集合是否存在"""
    from app.clients.mongo_client import get_history_mongo_tool
    from app.conf.mongo_config import mongo_config

    tool = get_history_mongo_tool()
    tool.client.admin.command("ping")
    exists = "chat_message" in tool.db.list_collection_names()
    return f"库={mongo_config.db_name} | chat_message={'已建' if exists else '未建（首次写入时自动创建）'}"


def check_minio() -> Optional[str]:
    """MinIO：桶是否存在（桶由服务启动时自动创建，此处只做探测不创建）"""
    from app.clients.minio_client import get_minio_client
    from app.conf.minio_config import minio_config

    client = get_minio_client()
    ok = client.bucket_exists(minio_config.bucket_name)
    return f"桶={minio_config.bucket_name} ({'已建' if ok else '未建，首次导入时自动创建'})"


def check_llm() -> Optional[str]:
    """LLM：发起一次最小对话请求，验证密钥、地址与模型名均可用"""
    from app.clients.llm_client import get_llm_client
    from app.conf.lm_config import lm_config

    client = get_llm_client()
    resp = client.invoke("ping")
    text = (getattr(resp, "content", "") or "").strip().replace("\n", " ")
    return f"模型={lm_config.llm_model} | 返回={text[:24]!r}"


def check_mcp() -> Optional[str]:
    """MCP：连接百炼 WebSearch 服务并列出可用工具（异步，内部用 asyncio.run 驱动）"""
    from agents.mcp import MCPServerStreamableHttp

    from app.conf.bailian_mcp_config import mcp_config

    async def _probe() -> str:
        server = MCPServerStreamableHttp(
            name="search_mcp",
            params={
                "url": mcp_config.mcp_base_url,
                "headers": {"Authorization": mcp_config.api_key},
                "timeout": 60,
            },
            max_retry_attempts=2,
        )
        try:
            await server.connect()
            tools = await server.list_tools()
            names = [getattr(t, "name", "?") for t in (tools or [])]
            return f"工具数={len(names)} {names}"
        finally:
            await server.cleanup()

    return asyncio.run(_probe())


def check_embedding() -> Optional[str]:
    """BGE-M3：加载本地模型并编码一条短文本，验证模型文件与推理设备可用（较慢）"""
    from app.clients.embedding_client import generate_embeddings
    from app.conf.embedding_config import embedding_config

    result = generate_embeddings(["连通性自检"])
    return (
        f"设备={embedding_config.bge_device} | "
        f"dense维度={len(result['dense'][0])} | sparse非零项={len(result['sparse'][0])}"
    )


def check_reranker() -> Optional[str]:
    """BGE-Reranker：加载本地模型并对一组问答打分（较慢）"""
    from app.clients.reranker_client import get_reranker_model
    from app.conf.reranker_config import reranker_config

    model = get_reranker_model()
    score = model.compute_score([["连通性自检", "这是一段用于自检的参考文本"]], normalize=True)
    return f"设备={reranker_config.bge_reranker_device} | 分数={score}"


# ==================== 主流程 ====================
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EcomKbAgent 外部依赖连通性自检（请在项目根目录用 python -m scripts.check_connections 运行）"
    )
    parser.add_argument("--skip-llm", action="store_true", help="跳过 LLM 探测（避免消耗额度/网络请求）")
    parser.add_argument("--skip-mcp", action="store_true", help="跳过 MCP 联网工具探测")
    parser.add_argument("--with-models", action="store_true",
                        help="追加本地模型加载检测（BGE-M3 / Reranker，首次加载较慢且占用显存）")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    print("=" * 72)
    print("EcomKbAgent 外部依赖连通性自检")
    print("=" * 72)

    # 打印将被探测的目标（仅地址/名称，不含任何密钥）
    try:
        from app.conf.lm_config import lm_config
        from app.conf.milvus_config import milvus_config
        from app.conf.minio_config import minio_config
        from app.conf.mongo_config import mongo_config
        _print_header("探测目标", [
            ("Milvus", milvus_config.milvus_url or "<未配置>"),
            ("MongoDB", mongo_config.mongo_url or "<未配置>"),
            ("MinIO", minio_config.endpoint or "<未配置>"),
            ("LLM", f"{lm_config.base_url or '<未配置>'} / {lm_config.llm_model or '<未配置>'}"),
        ])
    except Exception as e:
        print(f"[{_FAIL}] 配置加载失败，无法继续：{type(e).__name__}: {e}")
        return 1

    results: List[Tuple[str, bool]] = []

    # 1. 必需依赖（缺失即无法对外提供完整能力）
    print("\n--- 必需依赖 ---")
    results.append(("Milvus", _run_check("Milvus", check_milvus)))
    results.append(("MongoDB", _run_check("MongoDB", check_mongo)))

    # 2. 可选依赖（失败仅影响部分功能）
    print("\n--- 可选依赖 ---")
    results.append(("MinIO", _run_check("MinIO", check_minio)))
    if args.skip_llm:
        print("[SKIP] LLM                        用户通过 --skip-llm 跳过")
    else:
        results.append(("LLM", _run_check("LLM", check_llm)))
    if args.skip_mcp:
        print("[SKIP] MCP WebSearch              用户通过 --skip-mcp 跳过")
    else:
        results.append(("MCP WebSearch", _run_check("MCP WebSearch", check_mcp)))

    # 3. 本地模型（默认不加载，显式开启）
    if args.with_models:
        print("\n--- 本地模型（--with-models）---")
        results.append(("BGE-M3 Embedding", _run_check("BGE-M3 Embedding", check_embedding)))
        results.append(("BGE-Reranker", _run_check("BGE-Reranker", check_reranker)))
    else:
        print("\n--- 本地模型 ---")
        print("[SKIP] BGE-M3 / Reranker          默认跳过（如需检测请加 --with-models）")

    # 4. 汇总
    failed = [name for name, ok in results if not ok]
    print("\n" + "=" * 72)
    print(f"自检结果：通过 {len(results) - len(failed)}/{len(results)} 项")
    if failed:
        print(f"失败项：{', '.join(failed)}")
        print("排查建议：确认 docker compose ps 状态、.env 中的地址与密钥、以及网络可达性")
        print("=" * 72)
        return 1
    print("全部通过 ✓")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
