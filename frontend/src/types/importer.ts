/**
 * 导入域类型定义
 */
import type { TaskStatus } from "./api";

export type ImportPhase = "validating" | "uploading" | "processing" | "completed" | "failed";

export interface ImportTask {
  id: string; // 后端 task_id（上传前为空）
  fileId: string; // 前端本地 id
  fileName: string;
  fileSize: number;
  phase: ImportPhase;
  status: TaskStatus;
  progress: number; // 0-100
  doneList: string[];
  runningList: string[];
  error?: string;
}
