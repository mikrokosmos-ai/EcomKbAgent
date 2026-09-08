/**
 * 后端接口客户端
 * 封装导入/查询/任务/历史/健康检查共 7 个接口
 */
import { http } from "./http";
import type { HealthResult, HistoryResult, TaskStatusResult, UploadResult } from "../types/api";
import type { QueryResponse } from "../types/query";

export const IMPORT_API = (import.meta.env.VITE_IMPORT_API || "/import-api").replace(/\/$/, "");
export const QUERY_API = (import.meta.env.VITE_QUERY_API || "/query-api").replace(/\/$/, "");

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
