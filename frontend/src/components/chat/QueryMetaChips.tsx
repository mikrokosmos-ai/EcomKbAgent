/**
 * 识别主体 / 改写问题 chips
 */
import { GitBranch, Tag } from "lucide-react";
import type { ChatMessage } from "../../types/query";

export function QueryMetaChips({ message }: { message: ChatMessage }) {
  const names = (message.itemNames ?? []).filter(Boolean);
  const rewritten = message.rewrittenQuery?.trim();

  if (names.length === 0 && !rewritten) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {names.map((n) => (
        <span
          key={n}
          className="inline-flex items-center gap-1 border border-moss/25 bg-moss/10 px-2 py-1 text-xs text-ink/75"
        >
          <Tag className="h-3 w-3 text-moss" aria-hidden="true" />
          识别主体：{n}
        </span>
      ))}
      {rewritten && (
        <span className="inline-flex items-center gap-1 border border-brass/30 bg-brass/10 px-2 py-1 text-xs text-ink/75">
          <GitBranch className="h-3 w-3 text-brass" aria-hidden="true" />
          改写：{rewritten}
        </span>
      )}
    </div>
  );
}
