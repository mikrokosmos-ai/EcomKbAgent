/**
 * 进度条
 */
import { cn } from "../../lib/format";

export function ProgressBar({
  value,
  className,
  tone = "brass",
}: {
  value: number;
  className?: string;
  tone?: "brass" | "moss" | "tomato";
}) {
  const pct = Math.max(0, Math.min(100, value));
  const color = tone === "moss" ? "bg-moss" : tone === "tomato" ? "bg-tomato" : "bg-brass";
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden bg-ink/10", className)}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={cn("h-full transition-all duration-300", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}
