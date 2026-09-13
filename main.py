import argparse
import asyncio

import uvicorn

from app.api.app_factory import create_app


class _SharedExitServer(uvicorn.Server):
    """
    both 模式下的 uvicorn Server：让同一组 server 共享"退出信号"。

    背景：两个 server 在同一事件循环里并发运行，而 uvicorn 的退出信号处理器是
    "后安装者生效"（每个 Server 在 serve() 里用 signal.signal 装上自己的 handle_exit）。
    直接 gather 两个 Server.serve() 时，一次 Ctrl+C 只会通知到其中一个 server，另一个
    会继续运行。这里让所有 peer 共用同一份 peers 列表：任意一个收到退出信号，就同时
    置所有 server 的 should_exit，保证一次 Ctrl+C 两个服务都干净退出。
    """
    def __init__(self, config: uvicorn.Config, peers=None):
        super().__init__(config)
        self._peers = peers if peers is not None else [self]

    def handle_exit(self, sig, frame):
        for server in self._peers:
            server.should_exit = True


def _build_both_servers():
    """构建 both 模式的两个 server：import(8000) + query(8001)。"""
    # 静态资源只在 query 侧挂载：both 下两个 app 各启用一半，
    # 若依赖默认的"import+query 同时启用才挂载"会导致两边都不挂 SPA（改造文档 §8 C-7）
    import_app = create_app(include_import=True, include_query=False, mount_frontend=False)
    query_app = create_app(include_import=False, include_query=True, mount_frontend=True)
    servers = [
        _SharedExitServer(uvicorn.Config(import_app, host="127.0.0.1", port=8000)),
        _SharedExitServer(uvicorn.Config(query_app, host="127.0.0.1", port=8001)),
    ]
    peers = list(servers)
    for s in servers:
        s._peers = peers
    return servers


async def _serve_both():
    """同一进程内并发启动 import 与 query 两个服务。"""
    servers = _build_both_servers()
    await asyncio.gather(*(s.serve() for s in servers))


def main():
    parser = argparse.ArgumentParser(description="EcomKbAgent 统一服务入口")
    parser.add_argument(
        "--service",
        choices=["all", "import", "query", "both"],
        default="all",
        help=(
            "启动的服务：all(单进程合并两个路由，:8000)、import(导入 :8000)、"
            "query(查询 :8001)、both(同进程双端口并发 import:8000 + query:8001)"
        ),
    )
    args = parser.parse_args()

    if args.service == "import":
        app = create_app(include_import=True, include_query=False)
        uvicorn.run(app, host="127.0.0.1", port=8000)
    elif args.service == "query":
        app = create_app(include_import=False, include_query=True)
        uvicorn.run(app, host="127.0.0.1", port=8001)
    elif args.service == "both":
        # both：同进程并发起两个服务，便于本地开发/演示。生产建议分离为两个进程——
        # BGE-M3 / Reranker 是同步 CPU 密集操作，跑在同一事件循环里会互相拖慢（改造文档 §8 C-7）。
        asyncio.run(_serve_both())
    else:  # all
        app = create_app(include_import=True, include_query=True)
        uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
