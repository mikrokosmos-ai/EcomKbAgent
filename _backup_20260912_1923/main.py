import argparse

import uvicorn

from app.api.app_factory import create_app


def main():
    parser = argparse.ArgumentParser(description="EcomKbAgent 统一服务入口")
    parser.add_argument(
        "--service",
        choices=["all", "import", "query"],
        default="all",
        help="启动的服务：all(合并)、import(导入)、query(查询)",
    )
    args = parser.parse_args()

    if args.service == "import":
        app = create_app(include_import=True, include_query=False)
        uvicorn.run(app, host="127.0.0.1", port=8000)
    elif args.service == "query":
        app = create_app(include_import=False, include_query=True)
        uvicorn.run(app, host="127.0.0.1", port=8001)
    else:  # all
        app = create_app(include_import=True, include_query=True)
        uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
