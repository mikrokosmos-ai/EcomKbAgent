/**
 * 加载中指示
 */
import { LoaderCircle } from "lucide-react";
import { cn } from "../../lib/format";

export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle className={cn("animate-spin", className)} aria-hidden="true" />;
}
