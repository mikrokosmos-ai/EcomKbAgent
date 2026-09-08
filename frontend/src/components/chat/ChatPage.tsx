/**
 * 问答页
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { Eraser } from "lucide-react";
import { useSession } from "../../store/SessionProvider";
import { useChat } from "../../hooks/useChat";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import { deleteHistory, getHistory } from "../../lib/kbApi";
import { parseAnswerAndImages } from "../../lib/answer";
import { makeId } from "../../lib/session";
import { TopBar } from "../layout/TopBar";
import { EmptyChat } from "./EmptyChat";
import { MessageList } from "./MessageList";
import { Composer } from "./Composer";
import { StreamToggle } from "./StreamToggle";
import { ImportHintBar } from "./ImportHintBar";
import { Modal } from "../ui/Modal";
import { useToast } from "../ui/Toast";
import type { ChatMessage } from "../../types/query";

const examples = [
  "HAK 180 烫金机怎么更换色带？",
  "万用表如何测量电压？",
  "路由器指示灯一直闪是什么问题？",
  "MateBook B3-410 和 B3-420 有什么区别？",
];

export function ChatPage() {
  const { sessionId } = useParams();
  const { onMenu } = useOutletContext<{ onMenu: () => void }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { sessions, activeId, setActive, appendMessages, clearMessages } = useSession();
  const { send, stop, isStreaming } = useChat();
  const toast = useToast();

  const [draft, setDraft] = useState("");
  const [importHint, setImportHint] = useState<string | null>(null);
  const [showClear, setShowClear] = useState(false);
  const loadedRef = useRef<string | null>(null);

  const session = sessionId ? sessions.find((s) => s.id === sessionId) : undefined;
  const messages = session?.messages ?? [];
  const { ref, onScroll } = useAutoScroll(messages);

  // 同步 activeId 与 URL
  useEffect(() => {
    if (sessionId) {
      if (sessionId !== activeId) setActive(sessionId);
    } else if (activeId !== null) {
      setActive(null);
    }
  }, [sessionId, activeId, setActive]);

  // 消费 ?q= / ?hint=
  useEffect(() => {
    const q = searchParams.get("q");
    const hint = searchParams.get("hint");
    if (hint) setImportHint(hint);
    if (q) setDraft(q);
    if (q || hint) {
      const next = new URLSearchParams(searchParams);
      next.delete("q");
      next.delete("hint");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // 本地无消息时从后端回放历史
  useEffect(() => {
    if (!sessionId || !session) return;
    if (session.messages.length > 0) return;
    if (loadedRef.current === sessionId) return;
    loadedRef.current = sessionId;
    let alive = true;
    (async () => {
      try {
        const data = await getHistory(sessionId, 50);
        const msgs: ChatMessage[] = data.items.map((it) => {
          const parsed = parseAnswerAndImages(it.text);
          return {
            id: it._id || makeId(),
            role: it.role,
            content: parsed.text || it.text,
            imageUrls: parsed.images,
            itemNames: it.item_names ?? [],
            rewrittenQuery: it.rewritten_query,
            createdAt: (it.ts ?? 0) * 1000,
            status: "done",
          };
        });
        if (alive && msgs.length > 0) appendMessages(sessionId, msgs);
      } catch {
        // 回放失败静默
      }
    })();
    return () => {
      alive = false;
    };
  }, [sessionId, session, appendMessages]);

  const onSend = useCallback(() => {
    const q = draft.trim();
    if (!q || isStreaming) return;
    setDraft("");
    send(q);
  }, [draft, isStreaming, send]);

  const onClear = useCallback(async () => {
    if (!sessionId) return;
    try {
      await deleteHistory(sessionId);
    } catch {
      toast("error", "服务端清空失败，仅清空本地显示");
    }
    clearMessages(sessionId);
    setShowClear(false);
  }, [sessionId, clearMessages, toast]);

  const canSubmit = draft.trim().length > 0 && !isStreaming;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TopBar
        title="智能知识库问答"
        subtitle="FastAPI SSE / LangGraph · RRF + Rerank"
        onMenu={onMenu}
        actions={
          <>
            <StreamToggle />
            <button
              type="button"
              onClick={() => setShowClear(true)}
              disabled={!sessionId || isStreaming}
              className="grid h-9 w-9 place-items-center rounded-full text-ink/55 transition hover:bg-ink/5 hover:text-ink disabled:cursor-not-allowed disabled:opacity-35"
              title="清空对话"
              aria-label="清空对话"
            >
              <Eraser className="h-4 w-4" aria-hidden="true" />
            </button>
          </>
        }
      />

      {importHint && (
        <ImportHintBar
          fileName={importHint}
          onFill={() => setDraft(`${importHint.replace(/\.[^.]+$/, "")} 的操作步骤是什么？`)}
          onDismiss={() => setImportHint(null)}
        />
      )}

      <div ref={ref} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {sessionId && !session ? (
          <div className="mx-auto flex min-h-full max-w-5xl flex-col items-center justify-center gap-4 px-4 text-center text-ink/60">
            <p className="text-sm">会话不存在或已被删除。</p>
            <Link
              to="/chat"
              className="border border-ink/15 bg-white/60 px-4 py-2 text-sm transition hover:bg-white"
            >
              返回新会话
            </Link>
          </div>
        ) : messages.length === 0 ? (
          <EmptyChat examples={examples} onUseExample={setDraft} />
        ) : (
          <MessageList messages={messages} />
        )}
      </div>

      <Composer
        value={draft}
        disabled={!canSubmit}
        isStreaming={isStreaming}
        onChange={setDraft}
        onSubmit={onSend}
        onStop={stop}
      />

      <Modal
        open={showClear}
        title="清空对话"
        description="确定要清空当前会话的所有消息吗？此操作会同步清除服务端历史记录。"
        onClose={() => setShowClear(false)}
        onConfirm={onClear}
        confirmLabel="确认清空"
        danger
      />
    </div>
  );
}
