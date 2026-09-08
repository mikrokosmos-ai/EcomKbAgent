/**
 * 应用外壳：侧栏 + 主区 + 状态栏 + 移动端抽屉
 */
import { useState } from "react";
import { Outlet } from "react-router-dom";
import { SideNav } from "./SideNav";
import { StatusBar } from "./StatusBar";
import { MobileTabBar } from "./MobileTabBar";
import { useImportPoller } from "../../hooks/useImportPoller";

export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  useImportPoller();

  return (
    <div className="h-dvh overflow-hidden bg-parchment text-ink">
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(90deg,rgba(32,32,29,0.045)_1px,transparent_1px),linear-gradient(rgba(32,32,29,0.035)_1px,transparent_1px)] bg-[size:48px_48px]" />
      <div className="pointer-events-none fixed inset-0 grain" />

      <div className="relative grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] overflow-hidden lg:grid-cols-[300px_minmax(0,1fr)] lg:grid-rows-1">
        <div className="hidden min-h-0 lg:block">
          <SideNav />
        </div>
        <main className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <div className="min-h-0 flex-1 overflow-hidden">
            <Outlet context={{ onMenu: () => setDrawerOpen(true) }} />
          </div>
          <StatusBar />
        </main>
      </div>
      <MobileTabBar />

      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={() => setDrawerOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[80vw] flex-col">
            <SideNav onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
