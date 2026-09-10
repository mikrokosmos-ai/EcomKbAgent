# EcomKbAgent（掌柜智库）

> 面向电商售后/客服场景的 **多模态商品知识库 RAG 系统**。  
> 把厂商 PDF 产品手册（正文 + 插图）导入 Milvus 向量库，再用「多路召回 → RRF 融合 → Cross-Encoder 重排 → 联网兜底 → 引用生成」的链路回答用户提问，答案可回链原文与图片。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python\&logoColor=white)

![FastAPI](https://img.shields.io/badge/FastAPI-0.141%2B-009688?logo=fastapi\&logoColor=white)

![LangGraph](https://img.shields.io/badge/LangGraph-1.2%2B-1C3C3C)

![Milvus](https://img.shields.io/badge/Milvus-2.6-00A1FF?logo=milvus\&logoColor=white)

![uv](https://img.shields.io/badge/uv-managed-6C7AFF?logo=uv\&logoColor=white)

![React](https://img.shields.io/badge/React-19-61DAFB?logo=react\&logoColor=white)

![pnpm](https://img.shields.io/badge/pnpm-11-6C7AFF?logo=pnpm\&logoColor=white)

---

## 目录

- [一、项目简介](#一项目简介)
  - [1.1 背景](#11-背景)
  - [1.2 核心功能](#12-核心功能)
  - [1.3 关键特性](#13-关键特性)
  - [1.4 技术栈](#14-技术栈)
- [二、系统架构](#二系统架构)
- [三、目录结构](#三目录结构)
- [四、快速开始](#四快速开始)
  - [4.1 环境要求](#41-环境要求)
  - [4.2 安装依赖](#42-安装依赖)
  - [4.3 启动基础设施](#43-启动基础设施)
  - [4.4 配置环境变量](#44-配置环境变量)
  - [4.5 启动服务](#45-启动服务)
  - [4.6 前端开发与构建（React + pnpm）](#46-前端开发与构建react--pnpm)
- [五、基础使用](#五基础使用)
  - [5.1 Web 界面](#51-web-界面)
  - [5.2 API 调用示例](#52-api-调用示例)
  - [5.3 接口一览](#53-接口一览)
- [六、模块说明](#六模块说明)
  - [6.1 导入链路 Import Pipeline](#61-导入链路-import-pipeline)
  - [6.2 查询链路 Query Pipeline](#62-查询链路-query-pipeline)
  - [6.3 基础设施层](#63-基础设施层)
- [七、开发指南](#七开发指南)
- [八、测试](#八测试)
- [九、常见问题 FAQ](#九常见问题-faq)

---

## 一、项目简介

### 1.1 背景

电商客服日常需要查阅大量厂商产品手册（路由器、打印机、笔记本、平板、烫金机等）。这类文档有三大特点：

| 痛点         | 说明                                                        |
| ---------- | --------------------------------------------------------- |
| **格式不友好**  | 以扫描/排版复杂的 PDF 为主，正文、表格、插图混排，纯文本抽取会丢失大量信息                  |
| **图文强耦合**  | 操作步骤类问答（"按键在哪""指示灯怎么闪"）的答案往往在图片里，纯文本检索必然答不准               |
| **型号高度相似** | 同系列不同型号（如 MateBook B3-410 / B3-420）参数差异小，检索容易串型号，导致"张冠李戴" |

EcomKbAgent 针对这三点设计：**用 MinerU 做高质量 PDF→Markdown 解析，用 VLM 把插图转成可检索的语义文本，用「商品主体（item_name）过滤 + 混合检索」解决型号串扰**，最终产出带来源引用与配图链接的答案。

### 1.2 核心功能

1. **知识导入（Import Pipeline）**：上传 PDF / Markdown → MinerU 解析 → 插图语义化 → 语义切分 → 商品主体识别 → BGE-M3 稠密+稀疏向量化 → 写入 Milvus。
2. **知识问答（Query Pipeline）**：问题改写与主体识别 → 三路并发召回（向量检索 / HyDE / 联网搜索）→ RRF 融合 → Cross-Encoder 重排 → 带引用生成答案。
3. **多轮会话**：MongoDB 持久化历史消息，支持上下文指代消解（"它怎么关机？"）、历史查询与清空。
4. **任务可视化**：导入与查询共用一套任务追踪机制，前端可实时看到"检查文件 → PDF转Markdown → 图片处理 → …"的节点级进度。
5. **流式输出**：基于 SSE 推送 `ready / progress / delta / final / error` 事件，前端逐字渲染。

### 1.3 关键特性

- **多模态入库**：图片经 VLM（`qwen3-vl` 系列）生成语义描述后回写进 Markdown 原文，并同步上传 MinIO 保留原图 URL，答案可回链配图。
- **主体感知检索**：先由 LLM 从文档中识别商品主体名（`item_name`），检索时以 `item_name in [...]` 做标量过滤，从源头避免跨型号污染。
- **稠密 + 稀疏混合检索**：BGE-M3 同时产出 dense（1024 维）与 sparse 向量，Milvus `hybrid_search` + `WeightedRanker(0.8, 0.2)` 加权融合。
- **HyDE 增强召回**：先让 LLM 生成一段"假设性答案"，再用「原问题 + 假设答案」联合检索，缓解短 query 语义稀疏问题。
- **联网兜底**：通过 MCP（Streamable HTTP）调用阿里云百炼 WebSearch，知识库没有的内容自动走公网检索，并在重排阶段与本地切片统一排序。
- **动态 TopK 重排**：BGE-reranker-large 打分后按"断崖阈值"（相对 0.25 / 绝对 0.5）动态截取 TopK（1~10），避免无关文档稀释上下文。
- **提示词工程化**：全部 Prompt 外置为 `prompts/*.prompt` 模板文件，用 `load_prompt(name, **kwargs)` 渲染，改提示词不需要改代码。
- **统一生命周期管理**：`lifespan` 中按"必需/可选"分级初始化外部客户端——Milvus、MongoDB 失败即阻断启动；MinIO、本地模型失败仅告警降级。
- **第三方 API 限流**：内置滑动窗口限速器（默认 60 秒 9 次），防止批量导入时触发 VLM/LLM 平台限流。

### 1.4 技术栈

| 层次         | 技术选型                                                                       |
| ---------- | -------------------------------------------------------------------------- |
| 语言 / 依赖管理  | 后端 Python 3.11+ + [uv](https://docs.astral.sh/uv/)；前端 Node.js 20+ + [pnpm](https://pnpm.io/) |
| Web 框架     | 后端 FastAPI + Uvicorn（CORS、BackgroundTasks、SSE StreamingResponse）                              |
| 前端         | React 19 + TypeScript 5.7 + Vite 6 + Tailwind CSS 3 + react-router-dom v7 + lucide-react          |
| 编排框架       | LangGraph（StateGraph / 条件边 / 并行分支）、LangChain（消息、OutputParser、TextSplitter） |
| Agent 工具协议 | OpenAI Agents SDK（`openai-agents`）+ MCP Streamable HTTP                    |
| 文档解析       | MinerU（官方 SDK / API）                                                       |
| 向量模型       | BGE-M3（dense 1024 维 + sparse，FP16）                                         |
| 重排模型       | BAAI/bge-reranker-large（Cross-Encoder）                                     |
| 大语言模型      | 任意 OpenAI 兼容接口（默认阿里云 DashScope `qwen` 系列），VLM 用于图片理解                       |
| 向量数据库      | Milvus 2.6（AUTOINDEX / SPARSE_INVERTED_INDEX，IP 度量）                        |
| 对象存储       | MinIO（图片资产持久化）                                                             |
| 会话存储       | MongoDB（`chat_message` 集合）                                                 |
| 日志         | Loguru（控制台 + 文件双输出，按天滚动、自动清理）                                              |
| 基础设施       | Docker Compose（Milvus Standalone / etcd / MinIO ×2 / Attu / MongoDB）       |


## 二、系统架构

```
                         ┌──────────────────── Import Pipeline (LangGraph) ────────────────────┐
   PDF / MD ──upload──▶  │ node_entry ─▶ node_pdf_to_md ─▶ node_md_img ─▶ node_document_split  │
                         │   (类型判定)      (MinerU)      (VLM+MinIO)       (语义切分)          │
                         │                                     │                               │
                         │                                     ▼                               │
                         │        node_import_milvus ◀── node_bge_embedding ◀── node_item_name_recognition │
                         │          (写入向量库)          (BGE-M3 稠密+稀疏)        (LLM 识别商品主体)        │
                         └──────────────────────────────────┬─────────────────────────────────┘
                                                            │
                                                     Milvus (chunks)
                                                            │
   ┌──────────────────── Query Pipeline (LangGraph) ────────┴─────────────────────────────────┐
   │                                                                                          │
   │  node_item_name_confirm ──(问题改写 + 主体识别 + 澄清判定)──┬─▶ 需澄清 ─▶ node_answer_output │
   │                                                           │                              │
   │                              ┌────────────────────────────┴───────────┐                  │
   │                              ▼              ▼             ▼            │                  │
   │                node_search_embedding  node_search_embedding_hyde  node_web_search_mcp     │
   │                   (混合检索·item_name过滤)   (HyDE 假设文档)         (MCP 联网)              │
   │                              └────────────────┬───────────┘            │                  │
   │                                               ▼                        │                  │
   │                              node_rrf (RRF 倒排融合 k=60)               │                  │
   │                                               ▼                        │                  │
   │                    node_rerank (bge-reranker-large 动态 TopK) ◀─────────┘                  │
   │                                               ▼                                           │
   │                             node_answer_output (引用生成 + SSE 流式)                        │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
```


## 三、目录结构

```
EcomKbAgent/
├── main.py                       # 统一服务入口：--service {all|import|query}
├── pyproject.toml                # 后端项目元数据与依赖声明（uv 管理）
├── uv.lock                       # 后端依赖锁定文件
├── docker-compose.yaml           # 基础设施编排（Milvus / etcd / MinIO / Attu / MongoDB）
├── .env                          # 本地环境变量（含密钥，已在 .gitignore 中排除）
├── .env.example                  # 环境变量样例（脱敏占位符，可提交；cp .env.example .env 后填写）
│
├── app/
│   ├── api/                      # ── 接口层 ──
│   │   ├── app_factory.py        #     create_app()：CORS + lifespan + 按需挂载路由
│   │   ├── lifespan.py           #     启动/关闭时的外部客户端初始化与释放
│   │   ├── dependencies.py       #     依赖注入：向路由提供已编译的 LangGraph 应用
│   │   ├── routers/
│   │   │   ├── import_router.py  #     /upload（多文件上传 + 触发导入）
│   │   │   ├── query_router.py   #     /query、/stream、/history、/health
│   │   │   └── task_router.py    #     /status/{task_id}（导入与查询共用）
│   │   └── schemas/              #     Pydantic 请求/响应模型
│   │
│   ├── pipelines/                # ── 业务编排层（LangGraph）──
│   │   ├── import_pipeline/
│   │   │   ├── graph.py          #     导入状态图：节点注册 + 条件边 + 编译
│   │   │   ├── state.py          #     ImportGraphState（TypedDict）与默认状态工厂
│   │   │   └── nodes/            #     7 个导入节点（见 6.1）
│   │   └── query_pipeline/
│   │       ├── graph.py          #     查询状态图：并行三路召回 + 汇聚
│   │       ├── state.py          #     QueryGraphState（TypedDict）
│   │       └── nodes/            #     7 个查询节点（见 6.2）
│   │
│   ├── clients/                  # ── 外部客户端层 ──
│   │   ├── llm_client.py         #     门面：get_llm_client(model, json_mode)
│   │   ├── embedding_client.py   #     门面：get_bge_m3_ef() / generate_embeddings()
│   │   ├── reranker_client.py    #     门面：get_reranker_model()
│   │   ├── milvus_client.py      #     门面：get_milvus_client()
│   │   ├── minio_client.py       #     门面：get_minio_client()
│   │   ├── mongo_client.py       #     门面：get_history_mongo_tool()
│   │   └── manager/              #     各客户端的单例管理器（init / close / 懒加载兜底）
│   │
│   ├── conf/                     # ── 配置层 ──
│   │   ├── lm_config.py          #     LLM / VLM：base_url、api_key、模型名、temperature
│   │   ├── embedding_config.py   #     BGE-M3：本地路径、设备、FP16
│   │   ├── reranker_config.py    #     bge-reranker-large：路径、设备、FP16
│   │   ├── milvus_config.py      #     Milvus：地址 + 三个集合名
│   │   ├── minio_config.py       #     MinIO：endpoint、密钥、bucket、图片目录
│   │   ├── mongo_config.py       #     MongoDB：连接串、库名
│   │   ├── mineru_config.py      #     MinerU：API Base URL + Token
│   │   └── bailian_mcp_config.py #     MCP：百炼 WebSearch 服务地址
│   │
│   ├── repositories/             # ── 数据访问层 ──
│   │   ├── history_repo.py       #     会话历史的增删改查（MongoDB）
│   │   └── vector_search_repo.py #     混合检索请求构建、hybrid_search、按 chunk_id 批量取回
│   │
│   ├── prompts/
│   │   └── loader.py             #     load_prompt(name, **kwargs)：读取并渲染 prompts/ 下的模板
│   │
│   ├── core/
│   │   ├── logger.py             #     Loguru 配置 + @node_log / @step_log 装饰器
│   │   ├── exceptions.py         #     领域异常体系：AppError 基类 + 配置/导入/查询/存储四支
│   │   ├── paths.py              #     PROJECT_ROOT 探测（.env 作为根目录标识）
│   │   └── rate_limit.py         #     滑动窗口限速器
│   │
│   └── utils/
│       ├── task_utils.py         #     任务状态追踪（pending/processing/completed/failed）+ 节点名中文化
│       ├── sse_utils.py          #     SSE 会话队列与事件封装
│       ├── format_utils.py       #     文本/结果格式化
│       ├── escape_milvus_string_utils.py  # 过滤表达式转义
│       ├── normalize_sparse_vector.py     # 稀疏向量归一化
│
├── prompts/                      # 提示词模板（*.prompt，str.format 占位符）
│   ├── rewritten_query_and_itemnames.prompt  # 问题改写 + 商品主体抽取
│   ├── hyde_prompt.prompt                    # HyDE 假设性文档生成
│   ├── item_name_recognition.prompt          # 导入时识别文档主体
│   ├── image_summary.prompt                  # 图片语义摘要（VLM）
│   ├── product_recognition_system.prompt     # 商品识别系统提示词
│   └── answer_out.prompt                     # 最终答案生成（含引用约束）
│
├── frontend/                     # 前端工程（React 19 + TypeScript + Vite，需构建）
│   ├── src/                      #   源码：App、组件、hooks、lib（API 客户端）、store、types
│   │   ├── App.tsx               #   HashRouter 路由装配：/chat、/chat/:id、/import、404
│   │   ├── components/           #   布局（AppShell / SideNav / TopBar）、chat、importer、ui
│   │   ├── hooks/                #   useChat / useImportPoller / useHealth 等
│   │   ├── lib/                  #   kbApi（7 个接口封装）、http、sse、session、storage
│   │   └── store/                #   SessionProvider（会话状态）
│   ├── package.json              #   pnpm 管理，scripts: dev / build / preview / lint
│   ├── pnpm-workspace.yaml       #   pnpm v10+ 配置（allowBuilds: esbuild）
│   ├── pnpm-lock.yaml            #   前端依赖锁定文件
│   ├── vite.config.ts            #   开发代理：/import-api→8000、/query-api→8001
│   ├── .npmrc                    #   镜像源（registry.npmmirror.com）
│   └── .env.example              #   VITE_IMPORT_API / VITE_QUERY_API 等
│
├── doc/                          # 本地知识库语料（*.pdf，默认不入库，见 .gitignore）
├── output/                       # 运行时产物：按 日期/任务ID 分层的中间文件
├── logs/                         # 运行日志（app_YYYYMMDD.log，默认保留 7 天）
└── volumes/                      # Docker 挂载数据卷（MinIO 数据）
```


## 四、快速开始

### 4.1 环境要求

| 项目         | 要求                                                                    | 说明                                                                                      |
| ---------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| 操作系统       | Windows / Linux / macOS                                               | Windows 已在 Python 3.11.9 + Docker Desktop 验证                                            |
| Python     | **3.11 及以上**                                                          | `pyproject.toml` 声明 `requires-python = ">=3.11"`                                        |
| Node.js    | **20 及以上**                                                            | 前端构建工具 Vite 6 的运行要求                                                                 |
| 包管理器（后端） | [uv](https://docs.astral.sh/uv/)                                      | 推荐；也可用 pip + venv                                                                       |
| 包管理器（前端） | [pnpm](https://pnpm.io/)（v11，需 Node.js ≥ 20）                          | 前端依赖管理；镜像走 `frontend/.npmrc`（npmmirror）                                                |
| Docker     | Docker Desktop / Engine + Compose v2                                  | 用于 Milvus、MinIO、MongoDB、Attu                                                            |
| GPU（可选但推荐） | NVIDIA GPU + CUDA 13.0 驱动                                             | BGE-M3 与 bge-reranker-large 本地推理；无 GPU 请将 `BGE_DEVICE` / `BGE_RERANKER_DEVICE` 改为 `cpu` |
| 外部服务账号     | MinerU API Token、OpenAI 兼容 LLM API Key（默认 DashScope）、百炼 WebSearch MCP | 见 4.4                                                                                   |
| 磁盘         | ≥ 20GB                                                                | BGE-M3 + bge-reranker-large 约 11GB（含缓存）                                                 |

### 4.2 安装依赖

```bash
# 1) 克隆仓库
git clone https://github.com/mikrokosmos-ai/EcomKbAgent.git
cd EcomKbAgent

# 2) 创建虚拟环境并安装后端依赖（uv 会读取 pyproject.toml + uv.lock）
uv venv                 # 默认创建 .venv（Python 3.11）
uv sync                 # 安装锁定版本的全部依赖

# 3) 激活虚拟环境
# Windows (PowerShell)
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

> **关于 PyTorch**：`pyproject.toml` 中 `torch / torchvision / torchaudio` 固定从 CUDA 13.0 源（`https://download.pytorch.org/whl/cu130`）安装。  
> 若只需 CPU 版本，请在执行 `uv sync` 前临时调整 `[tool.uv.sources]` 中的 index 指向 CPU 源，避免下载数 GB 的 CUDA 依赖。

不使用 uv 的场景：

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r <(uv export --format requirements.txt)   # 或手动 pip install 主要依赖
```

### 4.3 启动基础设施

```bash
# 首次启动会拉取镜像，耗时较长
docker compose up -d

# 查看各服务健康状态（Milvus 首次启动约需 30~90 秒）
docker compose ps
```

| 服务              | 容器名                   | 宿主端口             | 用途                                       |
| --------------- | --------------------- | ---------------- | ---------------------------------------- |
| MinIO           | `ecomkb-minio`        | `9000` / `9001`  | 业务对象存储（图片资产），控制台 `http://127.0.0.1:9001` |
| Milvus          | `ecomkb-milvus`       | `19530` / `9091` | 向量数据库（gRPC / 健康检查）                       |
| etcd            | `ecomkb-etcd`         | —                | Milvus 元数据存储                             |
| Milvus 内置 MinIO | `ecomkb-milvus-minio` | `9002` / `9003`  | Milvus 内部对象存储                            |
| Attu            | `ecomkb-attu`         | `8000`           | Milvus 可视化管理界面                           |
| MongoDB         | `ecomkb-mongo`        | `27017`          | 会话历史存储                                   |

### 4.4 配置环境变量

在项目根目录创建 `.env`（**切勿提交到仓库**，仓库已通过 `.gitignore` 排除）：

```bash
cp .env.example .env        # 直接由样例文件生成，再按实际环境填写各项值
```

`.env.example` 已随仓库提供，含**全部变量的键名与格式说明**（值均为占位符，可安全提交）。
填写时请保持键名不变；如新增变量，请同步在本节配置表中登记。

| 分类        | 变量                                          | 示例                                                         | 说明                                                  |
| --------- | ------------------------------------------- | ---------------------------------------------------------- | --------------------------------------------------- |
| 日志        | `LOG_CONSOLE_ENABLE` / `LOG_CONSOLE_LEVEL`  | `True` / `DEBUG`                                           | 控制台日志开关与级别                                          |
|           | `LOG_FILE_ENABLE` / `LOG_FILE_LEVEL`        | `True` / `INFO`                                            | 文件日志（输出到 `logs/`）                                   |
|           | `LOG_FILE_RETENTION`                        | `7 days`                                                   | 日志保留时长                                              |
| 文档解析      | `MINERU_API_TOKEN`                          | `sk-...`                                                   | MinerU 平台 API Token                                 |
|           | `MINERU_BASE_URL`                           | `https://mineru.net/api/v4`                                | MinerU 服务地址                                         |
|           | `MODELSCOPE_OFFLINE` / `MODELSCOPE_CACHE`   | `1` / `D:/pycharm/model`                                   | ModelScope 离线模式与缓存目录                                |
| LLM / VLM | `OPENAI_API_KEY`                            | `sk-...`                                                   | OpenAI 兼容接口密钥（同时用于 MCP 鉴权）                          |
|           | `OPENAI_BASE_URL`                           | `https://dashscope.aliyuncs.com/compatible-mode/v1`        | OpenAI 兼容接口地址                                       |
|           | `LLM_DEFAULT_MODEL`                         | `qwen3.7-flash`                                            | 文本生成模型                                              |
|           | `VL_MODEL`                                  | `qwen3.7-max-2026-06-08`                                   | 多模态模型（图片理解）                                         |
|           | `LLM_DEFAULT_TEMPERATURE`                   | `0.1`                                                      | 生成温度                                                |
| MCP       | `MCP_DASHSCOPE_BASE_URL`                    | `https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp` | 百炼 WebSearch MCP 地址                                 |
| MinIO     | `MINIO_ENDPOINT`                            | `127.0.0.1:9000`                                           | 服务地址（**不带** `http://`）                              |
|           | `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`     | `minioadmin`                                               | 访问密钥                                                |
|           | `MINIO_BUCKET_NAME`                         | `knowledge-base-files`                                     | 桶名，启动时自动创建                                          |
|           | `MINIO_IMG_DIR`                             | `/upload-images`                                           | 图片存储前缀                                              |
|           | `MINIO_SECURE`                              | `False`                                                    | 是否启用 HTTPS                                          |
| 向量模型      | `BGE_M3_PATH`                               | `.../BAAI--bge-m3/snapshots/master`                        | 本地模型目录                                              |
|           | `BGE_M3`                                    | `BAAI/bge-m3`                                              | 模型仓库标识                                              |
|           | `BGE_DEVICE`                                | `cuda:0` / `cpu`                                           | 推理设备                                                |
|           | `BGE_FP16`                                  | `1`                                                        | 是否半精度                                               |
| 重排模型      | `BGE_RERANKER_LARGE`                        | `.../BAAI--bge-reranker-large/snapshots/master`            | 本地模型目录                                              |
|           | `BGE_RERANKER_DEVICE` / `BGE_RERANKER_FP16` | `cuda:0` / `1`                                             | 设备与精度                                               |
| Milvus    | `MILVUS_URL`                                | `http://127.0.0.1:19530`                                   | **必须带协议前缀**（pymilvus 3.x 要求）                        |
|           | `CHUNKS_COLLECTION`                         | `kd_db_chunks`                                             | 切片集合名                                               |
|           | `ITEM_NAME_COLLECTION`                      | `kd_db_item_names`                                         | 商品主体集合名                                             |
| MongoDB   | `MONGO_URL`                                 | `mongodb://127.0.0.1:27017`                                | 连接串                                                 |
|           | `MONGO_DB_NAME`                             | `knowledge_db_history`                                     | 数据库名                                                |
| 可选        | `WARMUP_ENABLE`                             | `false`                                                    | 设为 `true` 可在启动时预加载 Embedding / Reranker 本地模型（默认懒加载） |

> 说明：`ENTITY_NAME_COLLECTION`、`EMBEDDING_DIM`、`MILVUS_METRIC_TYPE`、`MILVUS_MIN_COSINE_SCORE`、`MILVUS_USER`、`MILVUS_PASSWORD` 目前为**预留配置项**，代码尚未读取（当前 `docker-compose.yaml` 的 Milvus 未开启鉴权）；切片集合的稠密向量维度在 `node_import_milvus.py` 中固定为 **1024**（BGE-M3 原生维度）。
> 另：`MINERU_MODEL_SOURCE`、`MODELSCOPE_CACHE`、`MODELSCOPE_OFFLINE`、`HF_HOME`、`MD_ROOT_DIR` 由 MinerU / ModelScope / HuggingFace 等第三方库隐式读取，代码中不显式 `os.getenv`。

首次运行建议先预下载模型（以 ModelScope 为例）：

```bash
modelscope download --model BAAI/bge-m3 --local_dir <你的缓存目录>/BAAI--bge-m3
modelscope download --model BAAI/bge-reranker-large --local_dir <你的缓存目录>/BAAI--bge-reranker-large
```

### 4.5 启动服务

`main.py` 提供三种启动模式，路由按需装配：

```bash
# 合并模式：同时挂载导入与查询路由，监听 0.0.0.0:8000
python main.py --service all

# 仅导入服务：监听 127.0.0.1:8000
python main.py --service import

# 仅查询服务：监听 127.0.0.1:8001
python main.py --service query
```

开发调试推荐带热重载：

```bash
uvicorn app.api.app_factory:create_app --factory --reload --host 127.0.0.1 --port 8000
```

启动后访问（后端 API 与文档）：

| 地址                                       | 内容             |
| ---------------------------------------- | -------------- |
| `http://127.0.0.1:8000/docs`             | Swagger 自动接口文档 |
| `http://127.0.0.1:8000/`                 | 前端 SPA（生产，需先 `pnpm run build` 产出 dist/，见 4.6） |
| `http://127.0.0.1:8001/health`           | 健康检查（后端）      |
| `http://localhost:5173/#/chat`           | 开发态问答页（React，`pnpm run dev`，见 4.6） |
| `http://localhost:5173/#/import`         | 开发态文件导入页（React）    |

> 服务启动时会强制初始化 Milvus 与 MongoDB 连接，失败将直接退出——这是刻意的"快速失败"设计，避免带着坏状态对外提供服务。  
> MinIO 与本地模型属于可选依赖，初始化失败只会打印告警并降级。

### 4.6 前端开发与构建（React + pnpm）

前端位于 `frontend/`，基于 React 19 + TypeScript + Vite 6。开发态由 Vite 提供 dev server（默认 `http://localhost:5173`），并把 `/import-api`、`/query-api` 两类请求代理到后端（默认 `127.0.0.1:8000`，可在 `.env` 覆盖）。生产态用 `pnpm run build` 产出 `dist/`，由后端 `app_factory.py` 直接托管（仅 `all` 模式，见下方说明）。

```bash
cd frontend

# 1) 安装依赖（依赖管理走 pnpm，镜像见 .npmrc）
#    若所在环境存在 HTTP(S)_PROXY 干扰，先清空再装：
pnpm install --registry=https://registry.npmmirror.com

# 2) 启动开发服务器（纯本地，不联网；默认 5173 端口）
pnpm run dev

# 3) 类型检查 + 生产构建（产出 frontend/dist/）
pnpm run build

# 4) 预览构建产物
pnpm run preview
```

常见环境变量（写在 `frontend/.env`，参考 `.env.example`）：

| 变量                        | 默认值                     | 说明                                                  |
| ------------------------- | ------------------------ | --------------------------------------------------- |
| `VITE_IMPORT_API`         | `/import-api`            | 导入接口前缀（经 Vite 代理到后端 8000）                          |
| `VITE_QUERY_API`          | `/query-api`             | 查询接口前缀（经 Vite 代理到后端 8000/8001）                   |
| `VITE_DEV_IMPORT_TARGET`  | `http://127.0.0.1:8000`  | 开发代理目标：后端 `all` 模式填 8000；`import` 拆分模式填 8000    |
| `VITE_DEV_QUERY_TARGET`   | `http://127.0.0.1:8000`  | 开发代理目标：后端 `all` 模式填 8000；`query` 拆分模式填 8001     |


> ℹ️ **生产部署**：后端 `app_factory.py` 已在 `all` 模式下挂载 `frontend/dist/`（挂在所有 API 路由之后，`/` 直接返回 `index.html`）。执行 `pnpm run build`（Vite 自动读取 `frontend/.env.production`，把 API 前缀设为同源 `/`）后，直接访问 `http://127.0.0.1:8000/` 即可，无需再开 Vite。拆分模式（`import`/`query`）不挂载 SPA，仍走 Vite dev server。


---

## 五、基础使用

### 5.1 Web 界面

前端为单页应用（SPA），使用 HashRouter，两个主页面通过左侧导航 / 移动端底栏互跳：

- **问答页**（`#/chat`、`#/chat/:sessionId`）：基于知识库提问，支持多轮会话、流式逐字输出、节点级流水线进度（检查文件 → PDF转Markdown → 图片处理 → 文档切分 → 主体识别 → 向量生成 → 导入），答案附带来源引用与配图链接；左侧为会话列表，可新建 / 切换 / 清空历史。
- **导入页**（`#/import`）：上传 PDF / Markdown，实时展示导入任务进度与节点状态，导入完成即可回到问答页提问。

访问步骤：

1. 启动基础设施（4.3）与后端服务（4.5，`python main.py --service all`）；
2. 在 `frontend/` 目录执行 `pnpm run dev`，打开 `http://localhost:5173/#/chat`；
3. 首次使用先到 `#/import` 上传商品手册，等待进度完成；
4. 回到 `#/chat` 提问，答案会附带来源与配图链接。

### 5.2 API 调用示例

**① 上传文件触发导入**

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -F "files=@doc/hak180使用说明书.pdf"
```

```json
{ "code": 200, "message": "Files uploaded successfully, total: 1", "task_ids": ["8f1c...-...-..."] }
```

**② 轮询导入进度**

```bash
curl "http://127.0.0.1:8000/status/8f1c...-...-..."
```

```json
{
  "code": 200,
  "task_id": "8f1c...",
  "status": "processing",
  "done_list": ["检查文件", "PDF转Markdown", "Markdown图片处理"],
  "running_list": ["文档切分"]
}
```

**③ 提问（同步）**

```bash
curl -X POST "http://127.0.0.1:8001/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "HAK180 烫金机怎么更换色带？", "session_id": "demo-001", "is_stream": false}'
```

**④ 提问（流式，SSE）**

```bash
# 1) 发起异步查询，拿到 session_id
curl -X POST "http://127.0.0.1:8001/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "HAK180 怎么设置温度？", "is_stream": true}'

# 2) 建立 SSE 长连接，接收 ready / progress / delta / final / error 事件
curl -N "http://127.0.0.1:8001/stream/<session_id>"
```

**⑤ 查询与清空历史**

```bash
curl "http://127.0.0.1:8001/history/demo-001?limit=10"
curl -X DELETE "http://127.0.0.1:8001/history/demo-001"
```

### 5.3 接口一览

| 方法       | 路径                      | 说明                                          |
| -------- | ----------------------- | ------------------------------------------- |
| `POST`   | `/upload`               | 多文件上传（form-data），每个文件生成一个 `task_id` 并触发导入流程 |
| `GET`    | `/status/{task_id}`     | 查询任务进度（导入用 `task_id`，查询用 `session_id`）      |
| `GET`    | `/health`               | 健康检查                                        |
| `POST`   | `/query`                | 提问，支持 `is_stream` 切换同步/异步流式                 |
| `GET`    | `/stream/{session_id}`  | SSE 事件流（节点进度 + 答案增量）                        |
| `GET`    | `/history/{session_id}` | 获取最近 N 条会话记录（默认 10）                         |
| `DELETE` | `/history/{session_id}` | 清空指定会话的历史记录                                 |

> `session_id` 需匹配 `[A-Za-z0-9-]{1,64}`；不传时服务端自动生成 UUID。  
> 前端通过 Vite 代理以 `/import-api`、`/query-api` 前缀调用上述接口（见 4.6）。

---

## 六、模块说明


### 6.1 导入链路 Import Pipeline

编排文件：`app/pipelines/import_pipeline/graph.py`；状态定义：`state.py` 的 `ImportGraphState`。

入口节点 `node_entry` 依据文件后缀设置 `is_pdf_read_enabled` / `is_md_read_enabled`，随后按条件边分流（非 PDF/MD 直接结束）。

| 节点                           | 职责                                                                                                              |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `node_entry`                 | 输入校验、文件类型判定、提取 `file_title`                                                                                     |
| `node_pdf_to_md`             | 调用 MinerU SDK 上传 PDF 并轮询解析结果，产出 Markdown 与插图目录                                                                  |
| `node_md_img`                | 扫描 Markdown 中的图片 → 截取上下文 → VLM 生成语义摘要 → 上传 MinIO → 用「摘要 + 图片 URL」回写 Markdown → 备份原文件                            |
| `node_document_split`        | 清洗 Markdown → 按标题语义切分 → 超长块用 `RecursiveCharacterTextSplitter` 二次切分（size 200 / overlap 20）→ 合并过碎片（< 100 字符）      |
| `node_item_name_recognition` | 取前 5 个切片（单块截断 800 字符、总量 2500 字符）交给 LLM 识别商品主体名，并写入 `item_name` 集合                                               |
| `node_bge_embedding`         | 按批（5 条/批）用「主体:{item_name},内容:{content}」拼接后生成 dense + sparse 向量，单批失败不影响整体                                        |
| `node_import_milvus`         | 建集合与索引（dense: AUTOINDEX/IP；sparse: SPARSE_INVERTED_INDEX/IP + DAAT_MAXSCORE）→ 按 `item_name` 删除旧数据（幂等重导入）→ 写入新切片 |

切片集合 Schema：

| 字段                                                    | 类型                  | 说明                |
| ----------------------------------------------------- | ------------------- | ----------------- |
| `chunk_id`                                            | INT64（主键，auto_id）   | 切片唯一标识            |
| `file_title` / `item_name` / `title` / `parent_title` | VARCHAR(512)        | 文档名、商品主体、当前标题、父标题 |
| `part`                                                | INT8                | 分片序号              |
| `content`                                             | VARCHAR(65535)      | 切片正文（图片已被语义描述替换）  |
| `dense_vector`                                        | FLOAT_VECTOR(1024)  | BGE-M3 稠密向量       |
| `sparse_vector`                                       | SPARSE_FLOAT_VECTOR | BGE-M3 稀疏向量       |

### 6.2 查询链路 Query Pipeline

编排文件：`app/pipelines/query_pipeline/graph.py`；状态定义：`state.py` 的 `QueryGraphState`。

`node_item_name_confirm` 为入口与"守门人"：它做问题改写 + 商品主体抽取；若提问为空、主体不确定或库中没有对应主体，则直接短路到 `node_answer_output` 返回澄清话术，避免无效的检索开销。

| 节点                           | 职责                                                                                                      |
| ---------------------------- | ------------------------------------------------------------------------------------------------------- |
| `node_item_name_confirm`     | 读取历史 → LLM 输出 `{rewritten_query, item_names}` → 与库内主体比对 → 决定继续检索或直接澄清                                   |
| `node_search_embedding`      | 改写问题向量化后在 Milvus 做混合检索，以 `item_name in [...]` 过滤，`WeightedRanker(0.8, 0.2)`、`norm_score=True`、`limit=5` |
| `node_search_embedding_hyde` | LLM 先生成假设性答案，再以「原问题 + 假设答案」联合向量化检索，补充语义召回                                                               |
| `node_web_search_mcp`        | 通过 MCP Streamable HTTP 调用百炼 `bailian_web_search`，为库外问题提供兜底语料                                            |
| `node_rrf`                   | RRF 倒排融合（`(1/(k+rank)) * weight`，`k=60`，取 Top5），当前融合向量路与 HyDE 路                                         |
| `node_rerank`                | 统一本地切片与网页结果的数据格式 → bge-reranker-large 打分 → 断崖式动态 TopK（阈值 0.25 / 0.5，上限 10）                              |
| `node_answer_output`         | 组装引用化 Prompt（上下文上限 12000 字符）→ LLM 生成 → 抽取图片 URL → 落库历史 → SSE 推送 final 事件                                |

### 6.3 基础设施层

| 模块                        | 说明                                                                                 |
| ------------------------- | ---------------------------------------------------------------------------------- |
| `app/clients/manager/*`   | 各外部客户端的单例管理器，统一 `init()` / `close()`；门面函数（如 `get_llm_client()`）在 client 为空时自动懒加载兜底 |
| `app/core/logger.py`      | Loguru 双通道日志；`@node_log` / `@step_log` 装饰器自动打印节点与步骤的进入、耗时、异常                       |
| `app/core/exceptions.py`  | 领域异常体系：`AppError` 基类（携带 `node_name` / `cause`），下设配置、导入、查询、存储四支；`StateFieldError` 额外结构化字段名与期望类型 |
| `app/utils/task_utils.py` | 内存态任务追踪（`pending/processing/completed/failed`），含节点名 → 中文名映射，供前端展示                  |
| `app/utils/sse_utils.py`  | 每个 `session_id` 一个队列，`push_to_session()` 推送 `ready/progress/delta/final/error` 事件  |
| `app/core/rate_limit.py`  | 滑动窗口限速（默认 60 秒 9 次），用于 VLM/LLM 调用保护                                                |
| `app/repositories/`       | 数据访问封装：MongoDB 会话历史、Milvus 混合检索与按 ID 批量取回                                          |


---

## 七、开发指南

项目遵循以下约定，新增代码请保持一致：

1. **节点分层**：每个 LangGraph 节点内部按 `step_1_xxx` / `step_2_xxx` 拆分为纯函数步骤，并用 `@step_log` 装饰；节点函数用 `@node_log` 装饰并统一调用 `add_running_task()` / `add_done_task()`。
2. **状态即契约**：跨节点数据一律通过 `ImportGraphState` / `QueryGraphState`（`TypedDict`）流转，新增字段需同步更新默认状态工厂（`create_default_state` / `create_query_default_state`）。
3. **提示词外置**：Prompt 一律放到 `prompts/*.prompt`，用 `load_prompt(name, **kwargs)` 渲染，不要在代码里硬编码长文本。
4. **配置集中**：新增外部服务时在 `app/conf/` 下新增 dataclass 配置，从 `.env` 读取，并在 README 配置表中登记。
5. **客户端收敛**：所有外部连接通过 `app/clients/manager/` 的单例管理器创建，并在 `lifespan` 中按"必需 / 可选"分级初始化。
6. **本地自测**：每个节点文件底部保留 `if __name__ == "__main__":` 自测入口，便于单独跑通。
7. **前端规范**：React 组件按 `components/{layout,chat,importer,ui}` 分层；API 调用统一收敛到 `lib/kbApi.ts`，禁止在组件里直接 `fetch` 裸写地址；新增接口请在 `lib/types` 同步类型。
8. **异常规范**：业务失败一律抛 `app/core/exceptions.py` 中的领域异常（如 `PdfConversionError` / `MilvusError` / `StateFieldError`），并携带 `node_name`，便于定位与按类型分支处理。**例外**：`app/api/schemas/*` 的 Pydantic 校验器必须继续抛 `ValueError` —— 只有 `ValueError` / `AssertionError` 会被 FastAPI 转成 422，换成自定义异常会把 422 变成 500。
9. **日志规范**：运行时路径统一 `from app.core.logger import logger`，**禁止 `print`**（仅文件底部 `__main__` 自测块允许），也不要 `import logging` 或调用 `logging.basicConfig`，避免与 Loguru 的全局配置冲突。

新增一个查询节点的典型步骤：

```python
# app/pipelines/query_pipeline/nodes/node_xxx.py
from app.core.logger import logger, node_log, step_log
from app.utils.task_utils import add_running_task, add_done_task

@step_log("step_1_do_something")
def step_1_do_something(state):
    ...

@node_log("node_xxx")
def node_xxx(state):
    add_running_task(state["session_id"], "node_xxx", state.get("is_stream"))
    result = step_1_do_something(state)
    add_done_task(state["session_id"], "node_xxx", state.get("is_stream"))
    return {"your_field": result}
```

然后在 `query_pipeline/graph.py` 中 `add_node` 并接入边，同时在 `app/utils/task_utils.py` 的 `_NODE_NAME_TO_CN` 中补上中文名。

---

## 八、测试

> 当前仓库尚未提供统一的 pytest 测试套件（详见[路线图](#十路线图)）。  
> 现阶段的验证方式为：各节点文件内置 `__main__` 自测入口 + `import_pipeline/graph.py` 的全流程跑通脚本。

```bash
# 单节点自测（示例）
python -m app.pipelines.import_pipeline.nodes.node_entry
python -m app.pipelines.query_pipeline.nodes.node_rrf
python -m app.pipelines.query_pipeline.nodes.node_search_embedding

# 导入全链路跑通（使用 doc/ 下的样例 PDF，输出到 output/）
python -m app.pipelines.import_pipeline.graph
```

运行前请确认：Milvus / MongoDB / MinIO 已启动，`.env` 配置完整，本地模型已下载。日志输出到控制台与 `logs/app_YYYYMMDD.log`。

---

## 九、常见问题 FAQ

**Q1：启动时报 Milvus 连接失败？**  
检查 `MILVUS_URL` 是否带了 `http://` 前缀（pymilvus 3.x 会把纯 `host:port` 判为非法），并确认 `docker compose ps` 中 Milvus 已 healthy（首次启动需 30~90 秒）。

**Q2：导入时报 `NoSuchBucket`？**  
`knowledge-base-files` 桶由 `minio_client_manager.init()` 自动创建。若被手动删除，重启服务即可重建；也可以登录 `http://127.0.0.1:9001` 手动创建。

**Q3：显存不足（CUDA OOM）？**  
将 `.env` 中 `BGE_DEVICE`、`BGE_RERANKER_DEVICE` 改为 `cpu`；若仍不足，可关闭 `WARMUP_ENABLE`（默认已关闭，模型为懒加载）。

**Q4：图片处理阶段很慢？**  
`node_md_img` 会对每张图片调用 VLM，且内置 60 秒 9 次的滑动窗口限速。这是为避免触发平台限流的刻意设计，批量导入大手册时请预留时间。

**Q5：`doc/` 目录为什么是空的？**  
`doc/` 存放厂商产品手册 PDF（约 85 个 / 404MB），涉及厂商文档版权且体积较大，已通过 `.gitignore` 排除。请自行放置需要入库的 PDF。

**Q6：任务进度在哪里看？**  
调用 `/status/{task_id}`（导入用上传返回的 `task_id`，查询用 `session_id`），返回 `status` 与 `done_list` / `running_list`。

**Q7：任务状态在重启后丢失？**  
当前任务追踪是单进程内存态实现。多实例部署或需要持久化时，应将其替换为 Redis 等外部存储（见路线图）。

**Q8：前端页面打不开 / 白屏？**  
前端是独立的 React 工程。开发态在 `frontend/` 跑 `pnpm run dev`（默认 5173 端口）再访问 `http://localhost:5173`；生产态 `pnpm run build` 后由后端直接托管，访问 `http://127.0.0.1:8000/`。若 `dist/` 未构建，后端 `/` 会 404（启动日志会打印警告）。

**Q9：`pnpm install` 报错 ECONNRESET？**  
本机若存在 `HTTP_PROXY` / `HTTPS_PROXY` 代理变量会干扰安装。用 `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy pnpm install` 临时清空，或双击 `frontend/install-deps-pnpm.bat`。`dev` / `build` 不联网，不受影响。

**Q10：访问 `/` 报 404 / 页面打不开？**  
生产态需要先 `cd frontend && pnpm run build` 产出 `dist/`，后端（`all` 模式）才会在 `/` 挂载 SPA；`dist/` 不存在时后端会打印警告且 `/` 返回 404。旧的 `/import.html`、`/query/html` 页面路由已移除，请改走 SPA（见 4.6 / 5.1）。

