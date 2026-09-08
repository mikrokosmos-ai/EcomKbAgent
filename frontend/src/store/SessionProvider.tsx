/**
 * 跨页共享状态（会话 + 导入任务 + 偏好）
 * 通过 Context 暴露，SideNav 与两个页面共享；localStorage 持久化保证互跳后状态不丢。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { ChatMessage, Session } from "../types/query";
import type { ImportTask } from "../types/importer";
import { loadJSON, saveJSON } from "../lib/storage";
import { makeSessionId, makeTitle } from "../lib/session";

const SESSIONS_KEY = "ecomkbagent:sessions";
const ACTIVE_KEY = "ecomkbagent:active-session";
const TASKS_KEY = "ecomkbagent:tasks";
const PREFS_KEY = "ecomkbagent:prefs";

interface Prefs {
  stream: boolean;
}

interface SessionContextValue {
  sessions: Session[];
  activeId: string | null;
  activeSession: Session | undefined;
  tasks: ImportTask[];
  streamEnabled: boolean;
  startSession: (firstQuery?: string) => string;
  setActive: (id: string | null) => void;
  appendMessages: (sessionId: string, messages: ChatMessage[]) => void;
  patchMessage: (sessionId: string, messageId: string, patch: Partial<ChatMessage>) => void;
  deleteSession: (id: string) => void;
  clearMessages: (sessionId: string) => void;
  setStreamEnabled: (v: boolean) => void;
  addTask: (task: ImportTask) => void;
  patchTask: (key: string, patch: Partial<ImportTask>) => void;
  removeTask: (key: string) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession 必须在 SessionProvider 内使用");
  return ctx;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>(() => loadJSON<Session[]>(SESSIONS_KEY, []));
  const [activeId, setActiveId] = useState<string | null>(() =>
    loadJSON<string | null>(ACTIVE_KEY, null),
  );
  const [tasks, setTasks] = useState<ImportTask[]>(() => loadJSON<ImportTask[]>(TASKS_KEY, []));
  const [prefs, setPrefs] = useState<Prefs>(() => loadJSON<Prefs>(PREFS_KEY, { stream: true }));

  useEffect(() => {
    saveJSON(SESSIONS_KEY, sessions);
  }, [sessions]);
  useEffect(() => {
    saveJSON(ACTIVE_KEY, activeId);
  }, [activeId]);
  useEffect(() => {
    saveJSON(TASKS_KEY, tasks);
  }, [tasks]);
  useEffect(() => {
    saveJSON(PREFS_KEY, prefs);
  }, [prefs]);

  const activeSession = activeId ? sessions.find((s) => s.id === activeId) : undefined;

  const startSession = useCallback((firstQuery?: string): string => {
    const id = makeSessionId();
    const session: Session = {
      id,
      title: firstQuery ? makeTitle(firstQuery) : "新会话",
      createdAt: Date.now(),
      messages: [],
    };
    setSessions((prev) => [session, ...prev]);
    setActiveId(id);
    return id;
  }, []);

  const setActive = useCallback((id: string | null) => setActiveId(id), []);

  const appendMessages = useCallback((sessionId: string, messages: ChatMessage[]) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === sessionId ? { ...s, messages: [...s.messages, ...messages] } : s,
      ),
    );
  }, []);

  const patchMessage = useCallback(
    (sessionId: string, messageId: string, patch: Partial<ChatMessage>) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id !== sessionId
            ? s
            : { ...s, messages: s.messages.map((m) => (m.id === messageId ? { ...m, ...patch } : m)) },
        ),
      );
    },
    [],
  );

  const deleteSession = useCallback((id: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    setActiveId((cur) => (cur === id ? null : cur));
  }, []);

  const clearMessages = useCallback((sessionId: string) => {
    setSessions((prev) => prev.map((s) => (s.id === sessionId ? { ...s, messages: [] } : s)));
  }, []);

  const setStreamEnabled = useCallback((v: boolean) => setPrefs((p) => ({ ...p, stream: v })), []);

  const addTask = useCallback((task: ImportTask) => {
    setTasks((prev) => [task, ...prev]);
  }, []);

  const patchTask = useCallback((key: string, patch: Partial<ImportTask>) => {
    setTasks((prev) =>
      prev.map((t) => (t.id === key || t.fileId === key ? { ...t, ...patch } : t)),
    );
  }, []);

  const removeTask = useCallback((key: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== key && t.fileId !== key));
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      sessions,
      activeId,
      activeSession,
      tasks,
      streamEnabled: prefs.stream,
      startSession,
      setActive,
      appendMessages,
      patchMessage,
      deleteSession,
      clearMessages,
      setStreamEnabled,
      addTask,
      patchTask,
      removeTask,
    }),
    [
      sessions,
      activeId,
      activeSession,
      tasks,
      prefs.stream,
      startSession,
      setActive,
      appendMessages,
      patchMessage,
      deleteSession,
      clearMessages,
      setStreamEnabled,
      addTask,
      patchTask,
      removeTask,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
