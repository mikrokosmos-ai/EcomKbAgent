/**
 * 后端接口客户端
 * 封装导入/查询/任务/历史/健康检查共 7 个接口
 *
 * 寻址说明（重要）：后端 `main.py --service {all|import|query|both}` 的端口约定为
 *   导入侧 8000、查询侧 8001。前端在两种形态下寻址方式不同：
 *   · 开发态：走 Vite 代理（`/import-api`、`/query-api`），由 vite.config.ts 转发到后端；
 *   · 生产态：dist 由后端直接托管，两个 env 均为 `/`（同源，经下面的 replace 后为空串）。
 *     其中 `all` 模式同源天然正确；但 `both` 模式下 **SPA 只挂在 query 侧（8001）**，
 *     而 `/upload`、`/status` 仅存在于 import 侧（8000）—— 同源请求会命中 8001 上的
 *     静态资源挂载点并返回 405 Method Not Allowed。故此处对「同源 + 当前端口非 import 端口」
 *     的情况，自动把导入类请求指向同主机的 import 端口。
 */
import { http } from "./http";
import type { HealthResult, HistoryResult, TaskStatusResult, UploadResult } from "../types/api";
import type { QueryResponse } from "../types/query";

/** 导入侧端口，与 `main.py` 保持一致；如需改端口用 `VITE_IMPORT_PORT` 覆盖 */
const IMPORT_PORT = import.meta.env.VITE_IMPORT_PORT || "8000";

/**
 * 解析导入侧 base。
 * 仅在「生产态同源配置（base 为空串）」且「页面不在 import 端口」时改写为跨端口绝对地址；
 * 开发态代理前缀与显式绝对地址一律原样返回（不干扰既有行为）。
 */
function resolveImportBase(raw: string): string {
  if (raw !== "" || typeof window === "undefined") return raw;
  const { protocol, hostname, port } = window.location;
  if (port && port !== IMPORT_PORT) {
    return `${protocol}//${hostname}:${IMPORT_PORT}`;
  }
  return raw;
}

const rawImportApi = (import.meta.env.VITE_IMPORT_API || "/import-api").replace(/\/$/, "");
const rawQueryApi = (import.meta.env.VITE_QUERY_API || "/query-api").replace(/\/$/, "");

export const IMPORT_API = resolveImportBase(rawImportApi);
export const QUERY_API = rawQueryApi;

export async function uploadFile(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("files", file);
  return http<UploadResult>(`${IMPORT_API}/upload`, {
    method: "POST",
    body: form,
    timeoutMs: 120000,
  });
}

export async function getTaskStatus(taskId: string): Promise<TaskStatusResult> {
  return http<TaskStatusResult>(`${IMPORT_API}/status/${encodeURIComponent(taskId)}`);
}

export async function postQuery(body: {
  query: string;
  session_id: string | null;
  is_stream: boolean;
}): Promise<QueryResponse> {
  return http<QueryResponse>(`${QUERY_API}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getHistory(sessionId: string, limit = 10): Promise<HistoryResult> {
  return http<HistoryResult>(
    `${QUERY_API}/history/${encodeURIComponent(sessionId)}?limit=${limit}`,
  );
}

export async function deleteHistory(
  sessionId: string,
): Promise<{ message: string; delete_count: number }> {
  return http<{ message: string; delete_count: number }>(
    `${QUERY_API}/history/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
}

export async function health(): Promise<HealthResult> {
  return http<HealthResult>(`${QUERY_API}/health`, { timeoutMs: 5000 });
}
