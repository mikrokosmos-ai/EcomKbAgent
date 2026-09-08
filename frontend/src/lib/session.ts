/**
 * 会话 id 与标题工具
 */

export function makeId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// 会话 id 必须匹配后端 [A-Za-z0-9-]{1,64}（query_schema.py）
export function makeSessionId() {
  return (
    crypto.randomUUID?.() ??
    `sess-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  );
}

export function makeTitle(firstQuery: string) {
  const t = firstQuery.trim().replace(/\s+/g, " ");
  return t.length > 20 ? `${t.slice(0, 20)}…` : t;
}
