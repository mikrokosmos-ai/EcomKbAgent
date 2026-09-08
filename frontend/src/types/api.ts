/**
 * 通用接口类型定义
 * 对应后端返回结构（与 app/api 实勘一致）
 */

export type TaskStatus = "" | "pending" | "processing" | "completed" | "failed";

export interface TaskStatusResult {
  code: number;
  task_id: string;
  status: TaskStatus;
  done_list: string[];
  running_list: string[];
}

export interface UploadResult {
  code: number;
  message: string;
  task_ids: string[];
}

export interface HealthResult {
  ok: boolean;
}

export interface HistoryItem {
  _id: string;
  session_id: string;
  role: "user" | "assistant";
  text: string;
  rewritten_query: string;
  item_names: string[];
  ts: number;
}

export interface HistoryResult {
  session_id: string;
  items: HistoryItem[];
}
