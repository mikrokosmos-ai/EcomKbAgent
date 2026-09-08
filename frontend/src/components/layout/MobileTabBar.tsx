/**
 * 移动端底部导航（两页互跳）
 */
import { NavLink } from "react-router-dom";
import { MessagesSquare, UploadCloud } from "lucide-react";
import { cn } from "../../lib/format";
import { useSession } from "../../store/SessionProvider";

export function MobileTabBar() {
  const { activeId } = useSession();
  const chatTo = activeId ? `/chat/${activeId}` : "/chat";

  return (
    <nav
      className="grid h-14 shrink-0 grid-cols-2 border-t border-ink/10 bg-parchment/95 backdrop-blur lg:hidden"
      aria-label="主导航"
    >
      <NavLink
        to={chatTo}
        className={({ isActive }) =>
          cn(
            "flex flex-col items-center justify-center gap-0.5 text-xs transition",
            isActive ? "text-moss" : "text-ink/50",
          )
        }
      >
        {({ isActive }) => (
          <>
            <MessagesSquare className={cn("h-5 w-5", isActive ? "text-moss" : "text-ink/45")} aria-hidden="true" />
            <span>知识问答</span>
          </>
        )}
      </NavLink>
      <NavLink
        to="/import"
        className={({ isActive }) =>
          cn(
            "flex flex-col items-center justify-center gap-0.5 text-xs transition",
            isActive ? "text-moss" : "text-ink/50",
          )
        }
      >
        {({ isActive }) => (
          <>
            <UploadCloud className={cn("h-5 w-5", isActive ? "text-moss" : "text-ink/45")} aria-hidden="true" />
            <span>知识导入</span>
          </>
        )}
      </NavLink>
    </nav>
  );
}
