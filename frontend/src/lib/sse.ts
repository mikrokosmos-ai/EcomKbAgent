/**
 * SSE 流式通道客户端
 * 后端为 GET /stream/{key}（EventSource 模式），事件 ready/progress/delta/final/error。
 * key 为队列主键：§I-11 后传 task_id（同会话并发多轮互不覆盖）；兼容期可传 session_id（后端别名回退）。
 * 返回 close() 用于显式断开。
 */
import type { SseEvent } from "../types/query";

export interface QueryStreamHandlers {
  onEvent: (event: SseEvent) => void;
  onOpen?: () => void;
  onChannelError?: () => void;
}

export function openQueryStream(
  key: string,
  baseUrl: string,
  handlers: QueryStreamHandlers,
): () => void {
  const es = new EventSource(`${baseUrl}/stream/${encodeURIComponent(key)}`);

  es.addEventListener("open", () => handlers.onOpen?.());

  const bind = (name: string, type: SseEvent["type"]) => {
    es.addEventListener(name, (e) => {
      const raw = (e as MessageEvent).data;
      if (raw == null) return;
      let data: unknown = {};
      try {
        data = JSON.parse(String(raw) || "{}");
      } catch {
        data = {};
      }
      handlers.onEvent({ type, data } as SseEvent);
    });
  };

  bind("ready", "ready");
  bind("progress", "progress");
  bind("delta", "delta");
  bind("final", "final");
  // 服务端命名的 error 事件带 data；通道级错误走 onerror
  bind("error", "error");

  es.onerror = () => handlers.onChannelError?.();

  return () => es.close();
}
