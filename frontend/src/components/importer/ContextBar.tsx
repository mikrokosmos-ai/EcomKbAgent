/**
 * 上下文条（?q= 承接，从问答页澄清场景跳转而来）
 */
import { FilePlus2, X } from "lucide-react";

export function ContextBar({ question, onClear }: { question: string; onClear: () => void }) {
  return (
    <div className="flex items-center gap-3 border border-brass/30 bg-brass/10 px-4 py-3">
      <FilePlus2 className="h-4 w-4 shrink-0 text-brass" aria-hidden="true" />
      <div className="min-w-0 flex-1 text-sm text-ink/80">
        知识库可能缺少相关资料，请为《<span className="font-semibold">{question}</span>》补充文档。
      </div>
      <button
        type="button"
        onClick={onClear}
        className="shrink-0 p-1 text-ink/45 transition hover:text-ink"
        aria-label="关闭"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
