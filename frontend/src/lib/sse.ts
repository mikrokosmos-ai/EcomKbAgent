/**
 * SSE 流式通道客户端
 * 后端为 GET /stream/{session_id}（EventSource 模式），事件 ready/progress/delta/final/error。
 * 返回 close() 用于显式断开。
 */
import type { SseEvent } from "../types/query";

export interface QueryStreamHandlers {
  onEvent: (event: SseEvent) => void;
  onOpen?: () => void;
  onChannelError?: () => void;
}

export function openQueryStream(
  sessionId: string,
  baseUrl: string,
  handlers: QueryStreamHandlers,
): () => void {
  const es = new EventSource(`${baseUrl}/stream/${encodeURIComponent(sessionId)}`);

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
