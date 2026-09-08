/**
 * 状态徽标
 */
import type { ReactNode } from "react";
import { cn } from "../../lib/format";

export type BadgeTone = "pending" | "running" | "success" | "error" | "neutral";

const tones: Record<BadgeTone, string> = {
  pending: "border-ink/10 bg-white/55 text-ink/45",
  running: "border-brass/45 bg-brass/15 text-ink",
  success: "border-moss/25 bg-moss/10 text-ink",
  error: "border-tomato/35 bg-tomato/10 text-tomato",
  neutral: "border-ink/10 bg-white/55 text-ink/60",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 border px-2 py-0.5 text-xs font-semibold",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
