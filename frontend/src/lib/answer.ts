/**
 * 答案文本解析（从 web/chat.html 迁移，纯函数化）
 * 约定：图片仅以答案中显式书写的【图片】/ [图片] 区块为准，无区块不出图。
 */

function dedupeKeepOrder(arr: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const x of arr) {
    const v = String(x || "");
    if (!v || seen.has(v)) continue;
    seen.add(v);
    out.push(v);
  }
  return out;
}

export function isImageUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(u.pathname);
  } catch {
    return /\.(png|jpe?g|gif|webp|bmp|svg)(\?|#|$)/i.test(url || "");
  }
}

export function normalizeUrl(rawUrl: string): string {
  const s = String(rawUrl || "").trim();
  if (!s) return "";
  return s.replace(/\s/g, "%20");
}

function extractUrlsLoose(text: string): string[] {
  const regex = /(https?:\/\/[^\s]+)/g;
  const matches = String(text || "").match(regex) || [];
  const trimTail = (u: string) => u.replace(/[)\]}"'>，。,;；\]】）＞]+$/g, "");
  const trimHead = (u: string) => u.replace(/^[<([{'"«]+|^[＜（【[]+/g, "");
  return dedupeKeepOrder(matches.map((m) => trimHead(trimTail(m))).filter((u) => u));
}

function findLastImageMarkerIndex(raw: string): { idx: number; len: number } {
  const re = /【\s*图片\s*】|\[\s*图片\s*\]/g;
  let idx = -1;
  let len = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    idx = m.index;
    len = m[0].length;
  }
  return { idx, len };
}

export interface ParsedAnswer {
  text: string;
  images: string[];
}

export function parseAnswerAndImages(text: string): ParsedAnswer {
  const raw = String(text || "");
  const { idx, len } = findLastImageMarkerIndex(raw);
  if (idx === -1) return { text: raw, images: [] };

  const before = raw.slice(0, idx).trimEnd();
  const after = raw.slice(idx + len).trim();
  const urls: string[] = [];
  const lines = after
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  for (const line of lines) {
    if (line.startsWith("http://") || line.startsWith("https://")) {
      urls.push(line);
    } else {
      for (const u of extractUrlsLoose(line)) urls.push(u);
    }
  }

  const seen = new Set<string>();
  const images: string[] = [];
  for (const u of urls) {
    const normalized = normalizeUrl(u);
    if (!isImageUrl(normalized) || seen.has(normalized)) continue;
    seen.add(normalized);
    images.push(normalized);
  }
  return { text: before, images };
}

export function cleanListFormat(text: string): string {
  return String(text || "").replace(/\*\*/g, "");
}
