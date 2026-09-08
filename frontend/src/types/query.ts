/**
 * 问答域类型定义
 * 覆盖 SSE 事件、消息与会话模型
 */
import type { TaskStatus } from "./api";

export type ProgressStatus = "pending" | "running" | "success" | "error";

export interface StepState {
  step: string;
  status: ProgressStatus;
}

export type MessageStatus = "streaming" | "done" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number; // ms
  status?: MessageStatus;
  steps?: StepState[];
  imageUrls?: string[];
  itemNames?: string[];
  rewrittenQuery?: string;
  error?: string;
}

export interface Session {
  id: string;
  title: string;
  createdAt: number;
  messages: ChatMessage[];
}

export type SseEvent =
  | { type: "ready"; data: Record<string, never> }
  | { type: "progress"; data: { status: TaskStatus; done_list: string[]; running_list: string[] } }
  | { type: "delta"; data: { delta: string } }
  | { type: "final"; data: { answer: string; status: string; image_urls: string[] } }
  | { type: "error"; data: { error: string } };

export interface QueryResponse {
  message: string;
  session_id: string;
  answer?: string;
  done_list?: string[];
}
