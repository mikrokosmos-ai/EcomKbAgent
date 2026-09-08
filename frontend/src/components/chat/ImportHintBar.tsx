/**
 * 导入成功提示条（?hint= 承接）
 */
import { CheckCircle2, X } from "lucide-react";

export function ImportHintBar({
  fileName,
  onFill,
  onDismiss,
}: {
  fileName: string;
  onFill: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="mx-auto mt-4 flex max-w-6xl items-center gap-3 border border-moss/25 bg-moss/10 px-4 py-3 lg:px-8">
      <CheckCircle2 className="h-4 w-4 shrink-0 text-moss" aria-hidden="true" />
      <div className="min-w-0 flex-1 text-sm text-ink/80">
        <span className="font-semibold">《{fileName}》</span> 已入库，现在可以提问了。
      </div>
      <button
        type="button"
        onClick={onFill}
        className="shrink-0 border border-moss/30 bg-white/60 px-3 py-1.5 text-xs text-ink/75 transition hover:bg-white"
      >
        一键示例问题
      </button>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 p-1 text-ink/45 transition hover:text-ink"
        aria-label="关闭"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
