/**
 * 任务统计栏（含「去问答」互跳）
 */
import { ArrowRight, CheckCircle2, LoaderCircle, XCircle } from "lucide-react";

export function TaskSummaryBar({
  total,
  done,
  running,
  failed,
  onGoChat,
}: {
  total: number;
  done: number;
  running: number;
  failed: number;
  onGoChat: () => void;
}) {
  if (total === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-3 border border-ink/10 bg-white/55 px-4 py-3 shadow-line">
      <span className="text-sm font-semibold text-ink">共 {total} 个任务</span>
      <span className="inline-flex items-center gap-1 text-xs text-moss">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        完成 {done}
      </span>
      <span className="inline-flex items-center gap-1 text-xs text-brass">
        <LoaderCircle className="h-3.5 w-3.5" aria-hidden="true" />
        进行中 {running}
      </span>
      <span className="inline-flex items-center gap-1 text-xs text-tomato">
        <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
        失败 {failed}
      </span>
      {done > 0 && (
        <button
          type="button"
          onClick={onGoChat}
          className="ml-auto inline-flex items-center gap-1.5 bg-ink px-3 py-2 text-xs font-semibold text-parchment transition hover:bg-soot"
        >
          去问答
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
