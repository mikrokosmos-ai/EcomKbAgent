/**
 * 会话列表
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { cn } from "../../lib/format";
import { useSession } from "../../store/SessionProvider";
import { deleteHistory } from "../../lib/kbApi";
import { useToast } from "../ui/Toast";
import type { Session } from "../../types/query";

export function SessionList({
  sessions,
  activeId,
  onNavigate,
}: {
  sessions: Session[];
  activeId: string | null;
  onNavigate?: () => void;
}) {
  const navigate = useNavigate();
  const { deleteSession } = useSession();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  if (sessions.length === 0) {
    return <div className="px-1 py-3 text-xs text-ink/40">暂无历史会话</div>;
  }

  const onOpen = (id: string) => {
    onNavigate?.();
    navigate(`/chat/${id}`);
  };

  const onDelete = async (s: Session) => {
    setBusy(s.id);
    try {
      await deleteHistory(s.id);
      deleteSession(s.id);
      if (s.id === activeId) navigate("/chat");
    } catch {
      toast("error", "删除失败，请稍后重试");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-2">
      {sessions.map((s) => {
        const isActive = s.id === activeId;
        return (
          <div key={s.id} className="flex items-stretch gap-2">
            <button
              type="button"
              onClick={() => onOpen(s.id)}
              className={cn(
                "min-w-0 flex-1 border px-3 py-3 text-left text-sm leading-5 transition",
                isActive
                  ? "border-moss/60 bg-moss/20 text-ink"
                  : "border-ink/10 bg-white/42 text-ink/75 hover:border-moss/35 hover:bg-white/75",
              )}
            >
              <span className={cn("block truncate", isActive ? "font-semibold" : "font-medium text-ink/85")}>
                {s.title}
              </span>
              <span className="mt-0.5 block text-xs text-ink/45">{s.messages.length} 条消息</span>
            </button>
            <button
              type="button"
              onClick={() => onDelete(s)}
              disabled={busy === s.id}
              className="grid shrink-0 place-items-center border border-ink/10 bg-white/42 px-2.5 text-ink/40 transition hover:border-tomato/40 hover:bg-tomato/10 hover:text-tomato disabled:opacity-55"
              title="删除"
              aria-label="删除"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
