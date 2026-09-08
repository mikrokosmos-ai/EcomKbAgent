/**
 * 应用根组件：路由与 Provider 装配
 */
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "./components/ui/Toast";
import { SessionProvider } from "./store/SessionProvider";
import { AppShell } from "./components/layout/AppShell";
import { ChatPage } from "./components/chat/ChatPage";
import { ImportPage } from "./components/importer/ImportPage";
import { NotFoundPage } from "./components/NotFoundPage";

export default function App() {
  return (
    <HashRouter>
      <ToastProvider>
        <SessionProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/chat" replace />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:sessionId" element={<ChatPage />} />
              <Route path="import" element={<ImportPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </SessionProvider>
      </ToastProvider>
    </HashRouter>
  );
}
