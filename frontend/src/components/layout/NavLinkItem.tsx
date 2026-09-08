/**
 * 主导航项
 */
import { NavLink } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { cn } from "../../lib/format";

export function NavLinkItem({
  to,
  icon: Icon,
  label,
  hint,
  onClick,
}: {
  to: string;
  icon: LucideIcon;
  label: string;
  hint?: string;
  onClick?: () => void;
}) {
  return (
    <NavLink to={to} onClick={onClick} className="block">
      {({ isActive }) => (
        <span
          className={cn(
            "flex items-center gap-3 border px-3 py-3 text-sm transition",
            isActive
              ? "border-moss/60 bg-moss/20 text-ink"
              : "border-ink/10 bg-white/42 text-ink/75 hover:border-moss/35 hover:bg-white/75",
          )}
        >
          <Icon className={cn("h-4 w-4", isActive ? "text-moss" : "text-ink/45")} aria-hidden="true" />
          <span className="flex-1 truncate font-semibold">{label}</span>
          {hint ? <span className="text-xs text-ink/45">{hint}</span> : null}
        </span>
      )}
    </NavLink>
  );
}
