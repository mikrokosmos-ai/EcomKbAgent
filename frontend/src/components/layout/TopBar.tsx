/**
 * 顶部标题栏
 */
import type { ReactNode } from "react";
import { Menu } from "lucide-react";

export function TopBar({
  title,
  subtitle,
  actions,
  onMenu,
}: {
  title: string;
  subtitle: string;
  actions?: ReactNode;
  onMenu?: () => void;
}) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-ink/10 bg-parchment/88 px-4 backdrop-blur lg:px-6">
      <div className="flex min-w-0 items-center gap-3">
        {onMenu && (
          <button
            type="button"
            onClick={onMenu}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-ink/55 transition hover:bg-ink/5 hover:text-ink lg:hidden"
            aria-label="打开菜单"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
        )}
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-ink">{title}</div>
          <div className="truncate text-xs text-ink/45">{subtitle}</div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">{actions}</div>
    </header>
  );
}
