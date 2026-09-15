# EcomKbAgent 长期项目笔记

## 配置真相（易错，已实勘）
- **运行只加载 `.env`**，`load_dotenv()` 默认目标即 `.env`；`.env.example` 纯模板，全仓无任何代码读它。
- **以下 `.env` 键代码完全不读（inert 红鲱鱼）**：`EMBEDDING_DIM`、`MILVUS_METRIC_TYPE`、`MILVUS_MIN_COSINE_SCORE`、`MILVUS_USER`、`MILVUS_PASSWORD`。
  - 实证：`node_import_milvus.py` 硬编码 `dim=1024`（L52/159）与 `metric_type="IP"`（L61/68）；全仓 grep 无 `os.getenv("EMBEDDING_DIM"|"MILVUS_METRIC_TYPE")`。
  - 推论：上一轮把 `.env` 的 `EMBEDDING_DIM 1536→1024`、`MILVUS_METRIC_TYPE COSINE→IP` 是**基于错误前提**——env 值被忽略，只是"恰好与硬编码一致"才无害。改这些键不改变任何运行行为，反而制造误导。
- **`ENTITY_NAME_COLLECTION` 代码确实读**（`milvus_config.py:24`），**阶段 D 起已在用**（KG 实体集合）。**实测运行值 = `kb_graph_entity_names`**；`item_name_collection` 实测 = `kd_db_item_names`。
- **模型加载链路**：`BGEM3EmbeddingFunction(model_name=BGE_M3_PATH, ...)`（`embedding_client_manager.py:42`）从显式本地路径加载，不依赖 `MODELSCOPE_CACHE`/`HF_HOME`。
- **`MODELSCOPE_CACHE`/`HF_HOME` 实测 = `D:/pycharm/model` 磁盘不存在**（真实快照在 `D:/pycharm/ai_models/modelscope_cache/` 下）。属 stale 配置；BGE-M3 因走显式路径大概率非致命，但离线模式是隐患，建议对齐到 `D:/pycharm/ai_models/modelscope_cache`。
- **密钥/本机路径类（A 类，必须 `.env` 提供）**：`OPENAI_API_KEY`、`MINERU_API_TOKEN`、`BGE_M3_PATH`、`BGE_RERANKER_LARGE`、`MILVUS_URL`/`MONGO_URL`/`MINIO_ENDPOINT` 等。
- 新机器正确姿势：`cp .env.example .env`，只填 A 类中"每台机不同"的密钥/路径，B 类 27 项业务参数保持注释即走代码默认。

## 改造进度（依据 `output/项目对比与融入改造方案_20260910.md`）
- **阶段 A（零风险打底）**：已完成（`.env.example`、`app/core/exceptions.py`、print→logger、README）。
- **阶段 B（配置化与健壮性 B1–B6）**：**已完成、已提交 git**（`f1bf757`/`18adb39`/`21cf515`/`af4222f`/`28b727b`/`610a80c`）。改动范围 20 files, +816/−60。交付：`app/conf/{import,query}_pipeline_config.py`（27 项 + fail-fast 校验）、`node_guard`（logger.py，node_rerank 试点）、`node_item_name_confirm` NameError 修复、`ImportGraphState.is_stream`、`scripts/check_connections.py`。
- **阶段 C（接口与启动 C1–C3）**：**已落地（未提交 git；快照 `_backup_20260912_1923/`）**。新增 `app/api/schemas/{import_schema,history_schema}.py` + `app/services/{__init__,import_service,query_service}.py`；改 `import/task/query_router`、`create_app(..., mount_frontend=None)`、`main.py --service both`、README。硬约束 **C-1**（`task_ids` 保住）/ **C-3**（`run_query_graph` 保持同步）/ **C-7**（both 仅 query 侧挂 SPA）均守住；`_SharedExitServer` 保证一次 Ctrl+C 两服务同退。
- **阶段 D（功能扩展·知识图谱）**：**D1–D4 已全部落地（未提交 git；快照 `_backup_20260915_1005/` + `_backup_20260915_d4/`）**。新增 `app/conf/neo4j_config.py`、`app/clients/neo4j_client.py` + `manager/neo4j_client_manager.py`、`app/repositories/graph_repo.py`、`node_import_kg.py`、`node_query_kg.py`、`prompts/knowledge_graph.prompt`；改 `docker-compose.yaml`(neo4j 服务)、`lifespan`、两图、两 config、`node_rrf`、`node_rerank`、`node_answer_output`、`loader`、`answer_out.prompt`。守 **C-5**（扩 tuple 不引虚节点）/ **C-6**（成对改 + 三分类 + 第四区）/ **C-9**。
- 复核脚本（可复用）：`.venv/Scripts/python.exe` heredoc 跑 B1–B5 断言 + `kb_import_app`/`query_app` 编译 + `create_app` 三模式；完整导入/查询 E2E 需 docker 基础设施（Milvus/Mongo/MinIO/Neo4j）启动（Milvus/Mongo 是 lifespan **必需依赖**，未起则启动即失败）。

## 知识图谱（KG）要点（阶段 D 固化，勿踩）
- **依赖**：`neo4j` 6.3.0 用 `uv pip install --python .venv/Scripts/python.exe neo4j --index-url <镜像>` 装（venv 无 pip；**不改 pyproject.toml/uv.lock**）。
- **关系模型**：单一关系类型 `:REL {relation, item_name}`，关系名走**属性**而非 Cypher 动态 type（动态 type 只能字符串拼接 → 注入面）。白名单外关系 → `RELATED_TO`。
- **KG 是可选能力**：`node_import_kg` / `node_query_kg` 整体**优雅降级**（失败仅 warning、不抛错）；`lifespan` 对 neo4j 也是可选依赖（仅告警）。否则 Neo4j 未启动会让每次导入/查询失败。
- **⭐ 隐藏冲突（文档未写）**：`node_rerank.step_2_merged_rrf_and_mcp` 原先把 rrf_chunks **硬编码 `type="milvus"`**；KG 结果经 RRF→rerank 后会被误并入本地区。已改为 `chunk.get("type") or "milvus"` 透传 `kg`。
- **C-6 预算设计**：KG 证据区预算**从 LOCAL_EVIDENCE_BUDGET 划分**（`kg_budget = KG if kg_docs else 0`），保持 `LOCAL+WEB+HISTORY=MAX` 不变式，且**无图谱时零行为变化**（本地拿满预算）。
- **prompt 大括号**：含 JSON 示例的 prompt 必须把字面 `{`/`}` 转义为 `{{`/`}}`（`loader.load_prompt` 用 `str.format`，否则 KeyError）。`loader.py` 已加**占位符完备性检查**（`string.Formatter().parse` 正确跳过转义），缺失抛带明细的 `ValueError`。
- **实体集合**：`ENTITY_NAME_COLLECTION`（Milvus）**仅建稠密向量**（无 sparse）→ 查询侧必须用稠密单路 `client.search`，**不能**用 `create_hybrid_search_requests`。
- **⭐ Neo4j 实体要写 `label`**：`CYPHER_MERGE_ENTITIES_BATCH` 必须 `SET e.label = row.label`，且 `node_import_kg.step_6` 要传完整 `entities`（曾只传 name → 图中无 label，无法按类型查询）。
- **⭐ 实体名归一化要"截断后再 strip"**：`strip()[:15]` 的截断点可能落在空格上（`"AC 220 V-240 V 电脑"`→`"AC 220 V-240 V "`），已抽 `_normalize_name()` = `strip()[:MAX].strip()`。
- **✅ 已修：图谱证据走"独立通道"（对齐原型乙项目）**——`node_answer_output._build_kg_evidence` **直读 state**（`graph_relation_description` → `kg_triples` → `reranked_docs` 的 kg 分支逐级兜底），不再依赖 reranked_docs；配合 `RERANK_MIN_TOPK 1→3`。实测图谱证据 47 行稳定入 prompt、本地证据由 0→1 条。**判定性验证：把相关本地切片放进 reranked_docs 后答案完全正确**。
- **✅ 已修：`node_rerank` 全局同池排序压制本地证据（分区保底）**——cross-encoder 的全局排序会让本地的"安全警告式短句"输给高分网页（实测本地区整类被挤出、只剩最不相关那条）。新增 `step_5_ensure_local_quota`（`RERANK_MIN_LOCAL_KEEP` 默认 3）：在断崖截断**之后**从落选候选按分数补足 `type=="milvus"` 至 N 条，总数 ≤ `RERANK_MAX_TOPK`。**实测：本地 1→3 条，答案从"未找到"变为正确的清洁保养内容。**
- **⭐ 既有崩溃 BUG（已修）**：`node_rerank.step_4_chunk_topk` 循环上界误用 `max_topk - 1`（应为 `topk - 1`），当候选数 < `RERANK_MAX_TOPK` 且分数平滑无断崖时 → `IndexError`（500）。原代码只在断崖提前 break 时侥幸不触发。
- **⭐⭐ Milvus `row_count` 双重陷阱**：未 flush 时**滞后为 0**；删除后**仍含墓碑**（重建后 stats=180 但 query 实际 102）。判定"是否写入/真实条数"**必须用 `query`/`search`**。`MilvusConfig` 字段名：`chunks_collection`/`item_name_collection`/`entity_name_collection`。
- **导入链路对 LLM 403 无降级**：`node_md_img.step_3_image_summary` 异常直接冒泡中断整图（`node_import_kg` 有降级、`node_md_img` 没有）。百炼免费额度耗尽会导致导入在图片摘要处失败。

## 乙项目（掌柜智库原型）要点
- **位置**：`D:\下载\mozijie-shopkeeper_brain-main\mozijie-shopkeeper_brain-main`（**在 `D:\下载`，不在 `D:\pycharm`**；搜索时勿只搜 pycharm）。课件在 `doc/掌柜智库项目课件/`（01–21 编号 md，含全部设计讲解），代码在 `knowledge/`（`processor/import_process/` 完整、`processor/query_process/` 为骨架且 **`nodes/` 整目录缺失**）。
- **查询侧 KG 未接通**：`query_process/main_graph.py` 无 `query_kg` 节点；课件 17 的 RRF `sources` 只有 embedding+hyde（无 kg）。→ 乙项目**没有**"KG 经 RRF 到答案"的实现；按其参数（`rrf_max_results=10` ≤ embedding10+hyde5、kg 权重 0.7）KG 也进不去 RRF。
- **⭐ 乙项目的图谱证据通道（= 本项目的正确做法）**：答案节点**直读 `state["kg_triples"]`**，用 `_format_triples` 组装成 prompt 的**独立区块** `【图谱关系描述】{graph_relation_description}`，**不参与 RRF/rerank**。即"双通道"：`kg_chunks` 走融合（锦上添花）、`kg_triples` 走独立证据区（保底必达）。本项目零件已齐（`node_query_kg` 已返回 `graph_relation_description`），只差 `node_answer_output` 改数据来源。
- **参数差异**：`rrf_max_results` 乙 10 / 本 5；**`rerank_min_top_k` 乙 3 / 本 1**（乙至少保 3 条，本项目断崖一触发只剩 1）；其余（`rerank_max_top_k` 10、`gap_ratio` 0.25、`rrf_kg_weight` 0.7、`kg_max_seed_candidates` 3、`kg_max_total_triples` 50）一致。
- **并发写法**：乙用**虚节点** `multi_search`(分发) + `join`(汇合)，比本项目"条件边返回 tuple + 检索节点直连 rrf"更清晰（可作后续参考）。
- 乙的 `ANSWER_PROMPT` 模板：`【参考内容】{context}` / `【历史对话】{history}` / `【相关商品/实体】{item_names}` / `【图谱关系描述】{graph_relation_description}` / `【用户问题】{question}`；其简版 `_build_prompt` 漏传 `graph_relation_description` → 会 KeyError（本项目 `loader.py` 完备性检查已防住）。
- **⭐ 乙项目前端（chat.html / import.html）完全不涉及图谱**：图谱关系只作 LLM 输入，**接口不返回（`QueryResponse` 仅 `message/session_id/answer`）、页面不渲染**。→ 本项目**不要**为"展示图谱证据"改后端/前端（已核对一致）。搜 ES/TS 代码时勿用裸 `kg` 关键词（会误命中 CSS `bac-kg-round`）。
- **乙项目 SSE 契约**：事件 `ready / progress / delta / final`（**无 error**，本项目多一个 `error`）；队列键为 **`task_id`**（`/query` 流式响应返回 `task_id` 供建连）。→ 本项目 **D4 已于 2026-09-15 落地**：`QueryGraphState.task_id` + `resolve_trace_key(state)`（优先 task_id、缺失回退 session_id）+ `create_sse_queue(task_id, alias=session_id)` 别名兜底 + `/stream/{key}`；前端 `useChat.ts` 用 `task_id ?? session_id` 建流。

## 前端要点（易错，已实勘）
- **节点名契约**：`frontend/src/lib/nodes.ts` 的 `IMPORT_STEPS[].key` 与 `QUERY_FLOW_NODES[].step` **必须与后端 `app/utils/task_utils.py::_NODE_NAME_TO_CN` 的中文展示名逐字一致**（前端收到的 done_list/running_list 已是中文名）。后端新增节点（如 `node_import_kg`→"导入知识图谱"、`node_query_kg`→"查询知识图谱"）时**必须同步本文件**，否则会落到 `ImportStepRail` 的「其他事件」兜底、流程图节点永远 pending。
- **`both` 模式跨端口寻址**：生产构建 `VITE_IMPORT_API=/`、`VITE_QUERY_API=/` 为同源；但 `--service both` 下 **SPA 只挂 query 侧(8001)**，而 `/upload`、`/status` 只在 import 侧(8000) —— 同源请求会命中 8001 的 `mount("/")` StaticFiles 并返回 **405**。`lib/kbApi.ts::resolveImportBase()` 已按"页面端口 ≠ 8000 → 指向同主机 :8000"自动纠偏（可用 `VITE_IMPORT_PORT` 覆盖）。后端 CORS 为 `allow_origins=["*"]`，跨端口安全。
- **构建/检查命令**（bash coreutils 损坏，需走绝对路径）：
  - 类型检查：`cd frontend && "C:/Users/aixiwen/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" ./node_modules/typescript/bin/tsc --noEmit`
  - 构建：同前缀 `./node_modules/vite/bin/vite.js build`（实测 4.6s / 1644 模块）
  - ⚠️ 不要在这些命令后用 `| head`（`head` 不存在 → exit 127 且输出丢失）。
- **API 层规范**：所有接口调用收敛在 `lib/kbApi.ts`（组件内禁止裸 `fetch`）；`lib/http.ts` 统一超时/错误规范化；SSE 走 `lib/sse.ts`（EventSource + `GET /stream/{session_id}`）。

## 协作边界（用户既定）
- 任何项目代码/配置/部署改动**必须先出诊断报告、等用户明确批准**再动手；纯前端可直改但需 `tsc --noEmit` 过关。
- 配置类问题优先"临时 CLI 绕行"而非改 pyproject.toml/lockfile。
- 工作区有外部进程/编辑器在改文件（git 显示非本会话 staged、README「十、路线图」曾未落盘）——避免与代理同改一文件。
