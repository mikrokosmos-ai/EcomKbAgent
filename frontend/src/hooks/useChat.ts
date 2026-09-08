/**
 * 问答编排：发送 / 停止 / 流式事件消费
 */
import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../store/SessionProvider";
import { postQuery, QUERY_API } from "../lib/kbApi";
import { openQueryStream } from "../lib/sse";
import { parseAnswerAndImages } from "../lib/answer";
import { makeId } from "../lib/session";
import type { ChatMessage, StepState } from "../types/query";

function toSteps(doneList: string[], runningList: string[]): StepState[] {
  const steps: StepState[] = [];
  for (const s of runningList) steps.push({ step: s, status: "running" });
  for (const s of doneList) steps.push({ step: s, status: "success" });
  return steps;
}

export function useChat() {
  const navigate = useNavigate();
  const { activeId, startSession, appendMessages, patchMessage, streamEnabled } = useSession();
  const [isStreaming, setIsStreaming] = useState(false);
  const closeRef = useRef<(() => void) | null>(null);
  const inflightRef = useRef<{ sessionId: string; asstId: string } | null>(null);

  const stop = useCallback(() => {
    closeRef.current?.();
    closeRef.current = null;
    const cur = inflightRef.current;
    if (cur) {
      patchMessage(cur.sessionId, cur.asstId, { status: "done" });
    }
    inflightRef.current = null;
    setIsStreaming(false);
  }, [patchMessage]);

  const send = useCallback(
    async (raw: string) => {
      const query = raw.trim();
      if (!query || isStreaming) return;

      let sid = activeId;
      if (!sid) {
        sid = startSession(query);
        navigate(`/chat/${sid}`, { replace: true });
      }

      const userMsg: ChatMessage = {
        id: makeId(),
        role: "user",
        content: query,
        createdAt: Date.now(),
      };
      const asstId = makeId();
      const asstMsg: ChatMessage = {
        id: asstId,
        role: "assistant",
        content: "正在连接知识库…",
        createdAt: Date.now(),
        status: "streaming",
        steps: [],
      };
      appendMessages(sid, [userMsg, asstMsg]);
      inflightRef.current = { sessionId: sid, asstId };
      setIsStreaming(true);

      const finish = () => {
        inflightRef.current = null;
        closeRef.current = null;
        setIsStreaming(false);
      };

      try {
        if (!streamEnabled) {
          const res = await postQuery({ query, session_id: sid, is_stream: false });
          const parsed = parseAnswerAndImages(res.answer ?? "");
          patchMessage(sid, asstId, {
            content: parsed.text || "（已完成，但未返回答案）",
            imageUrls: parsed.images,
            status: "done",
            steps: toSteps(res.done_list ?? [], []),
          });
          finish();
          return;
        }

        const { session_id } = await postQuery({ query, session_id: sid, is_stream: true });
        let rawAnswer = "";

        const close = openQueryStream(session_id, QUERY_API, {
          onEvent: (ev) => {
            if (ev.type === "progress") {
              const running = ev.data.running_list ?? [];
              const done = ev.data.done_list ?? [];
              patchMessage(sid, asstId, {
                steps: toSteps(done, running),
                ...(running.length ? { content: `正在执行：${running[0]}` } : {}),
              });
            } else if (ev.type === "delta") {
              rawAnswer += ev.data.delta ?? "";
              const parsed = parseAnswerAndImages(rawAnswer);
              patchMessage(sid, asstId, { content: parsed.text || rawAnswer, imageUrls: parsed.images });
            } else if (ev.type === "final") {
              const finalText = ev.data.answer?.trim() ? ev.data.answer : rawAnswer;
              const parsed = parseAnswerAndImages(finalText);
              patchMessage(sid, asstId, {
                content: parsed.text || "（已完成，但未返回答案）",
                imageUrls: ev.data.image_urls?.length ? ev.data.image_urls : parsed.images,
                status: "done",
              });
              close();
              finish();
            } else if (ev.type === "error") {
              patchMessage(sid, asstId, {
                content: rawAnswer || "处理失败",
                error: ev.data.error || "未知错误",
                status: "error",
              });
              close();
              finish();
            }
          },
          onChannelError: () => {
            // 通道级错误：已有部分内容时保持现状，等待 final；否则由轮询兜底
            if (!rawAnswer) {
              patchMessage(sid, asstId, {
                content: "流式连接中断，正在尝试恢复…",
              });
            }
          },
        });
        closeRef.current = close;
      } catch (err) {
        patchMessage(sid, asstId, {
          content: "请求失败",
          error: err instanceof Error ? err.message : String(err),
          status: "error",
        });
        finish();
      }
    },
    [activeId, startSession, navigate, appendMessages, patchMessage, streamEnabled, isStreaming],
  );

  return { send, stop, isStreaming };
}
