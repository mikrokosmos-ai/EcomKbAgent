/**
 * 底部状态条：就绪 / 运行中 / 导入中
 */
import { Leaf, LoaderCircle } from "lucide-react";
import { useSession } from "../../store/SessionProvider";

export function StatusBar() {
  const { activeSession, tasks } = useSession();
  const streaming = activeSession?.messages.some((m) => m.status === "streaming") ?? false;
  const importing = tasks.filter((t) => t.phase === "processing" || t.phase === "uploading").length;
  const busy = streaming || importing > 0;
  const text = streaming ? "运行中" : importing > 0 ? `导入中（${importing} 个任务）` : "就绪";

  return (
    <div className="border-t border-ink/10 bg-[#efe6d8]/45 px-4 py-2 text-center text-xs text-ink/45">
      <span className="inline-flex items-center gap-2">
        {busy ? (
          <LoaderCircle className="h-3.5 w-3.5 animate-spin text-brass" aria-hidden="true" />
        ) : (
          <Leaf className="h-3.5 w-3.5 text-moss" aria-hidden="true" />
        )}
        <span role="status" aria-live="polite">
          {text}
        </span>
      </span>
    </div>
  );
}
