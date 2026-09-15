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

/**
 * 历史消息条目。
 * 两条契约要点（与后端 app/api/schemas/history_schema.py 对齐）：
 *   1. `_id` 是 MongoDB 主键，后端通过 Pydantic `alias="_id"` 映射，前端按 `_id` 读取；
 *   2. `item_names` / `ts` 在后端是 Optional（落库时可能未写入），
 *      故此处声明为可选 —— 否则会出现"类型说有、运行时是 undefined"的错配。
 */
export interface HistoryItem {
  _id: string;
  session_id: string;
  role: "user" | "assistant";
  text: string;
  rewritten_query: string;
  item_names?: string[] | null;
  ts?: number | null;
}

export interface HistoryResult {
  session_id: string;
  items: HistoryItem[];
}
