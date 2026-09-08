/**
 * 侧边导航：品牌 + 两页互跳主导航 + 历史会话 + 导入任务 + API 状态
 */
import { Activity, ListChecks, MessageSquarePlus, MessagesSquare, Server, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";
import { NavLinkItem } from "./NavLinkItem";
import { SessionList } from "../chat/SessionList";
import { useSession } from "../../store/SessionProvider";
import { useHealth } from "../../hooks/useHealth";

export function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  const { activeId, sessions, tasks } = useSession();
  const online = useHealth();
  const chatTo = activeId ? `/chat/${activeId}` : "/chat";
  const importingCount = tasks.filter((t) => t.phase === "processing" || t.phase === "uploading").length;

  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-ink/10 bg-[#efe6d8]/85 backdrop-blur">
      <div className="border-b border-ink/10 px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center bg-ink text-parchment">
            <span className="text-sm font-semibold">掌柜</span>
          </div>
          <div>
            <div className="text-base font-semibold tracking-[0.02em] text-ink">掌柜智库</div>
            <div className="text-xs text-ink/50">EcomKbAgent</div>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
        <nav className="space-y-2" aria-label="主导航">
          <NavLinkItem to={chatTo} icon={MessagesSquare} label="知识问答" onClick={onNavigate} />
          <NavLinkItem
            to="/import"
            icon={UploadCloud}
            label="知识导入"
            hint={importingCount > 0 ? `${importingCount} 进行中` : undefined}
            onClick={onNavigate}
          />
        </nav>

        <Link
          to="/chat"
          onClick={onNavigate}
          className="flex h-11 w-full items-center justify-center gap-2 bg-ink text-sm font-semibold text-parchment transition hover:bg-soot"
        >
          <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
          新会话
        </Link>

        <section>
          <div className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-[0.16em] text-ink/45">
            <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
            历史会话
          </div>
          <SessionList sessions={sessions} activeId={activeId} onNavigate={onNavigate} />
        </section>

        {importingCount > 0 && (
          <section>
            <div className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-[0.16em] text-ink/45">
              <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
              导入任务
            </div>
            <Link
              to="/import"
              onClick={onNavigate}
              className="flex items-center gap-2 border border-ink/10 bg-white/42 px-3 py-2 text-xs text-ink/70 transition hover:border-brass/35 hover:bg-white/75"
            >
              <Activity className="h-3.5 w-3.5 text-brass" aria-hidden="true" />
              {importingCount} 个任务进行中 · 查看 →
            </Link>
          </section>
        )}
      </div>

      <div className="border-t border-ink/10 p-4">
        <div className="grid gap-2 text-xs text-ink/55">
          <div className="flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2">
              <Server className="h-3.5 w-3.5" aria-hidden="true" />
              API
            </span>
            <span className={online ? "text-moss" : "text-tomato"}>{online ? "已连接" : "未连接"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-2">
              <Activity className="h-3.5 w-3.5" aria-hidden="true" />
              会话
            </span>
            <span>{sessions.length}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
