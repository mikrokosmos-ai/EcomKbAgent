/**
 * 通用卡片容器
 */
import type { ReactNode } from "react";
import { cn } from "../../lib/format";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("border border-ink/10 bg-white/55 shadow-line", className)}>{children}</div>;
}
