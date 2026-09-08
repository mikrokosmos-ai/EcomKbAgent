/**
 * fetch 封装：统一超时、错误规范化与后端 detail 解析
 */
export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function http<T>(url: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const { timeoutMs = 15000, ...rest } = init ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...rest, signal: controller.signal });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      let message = `HTTP ${res.status}`;
      try {
        const parsed = JSON.parse(text);
        if (typeof parsed.detail === "string") message = parsed.detail;
        else if (Array.isArray(parsed.detail)) {
          message = parsed.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ");
        }
      } catch {
        if (text) message = text;
      }
      throw new ApiError(message, res.status);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("请求超时，请检查后端服务是否启动");
    }
    throw new ApiError("网络异常，无法连接服务");
  } finally {
    clearTimeout(timer);
  }
}
