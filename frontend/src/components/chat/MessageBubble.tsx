/**
 * 消息气泡
 */
import { Bot, Copy, UserRound } from "lucide-react";
import { cn, formatTime } from "../../lib/format";
import { QueryMetaChips } from "./QueryMetaChips";
import { PipelineFlow } from "./PipelineFlow";
import { AnswerImages } from "./AnswerImages";
import { useToast } from "../ui/Toast";
import type { ChatMessage } from "../../types/query";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const toast = useToast();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      toast("success", "已复制");
    } catch {
      // 忽略剪贴板异常
    }
  };

  return (
    <article className={cn("group flex gap-3", isUser && "justify-end")}>
      {!isUser && (
        <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-parchment">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </div>
      )}

      <div className={cn("max-w-[920px] flex-1", isUser && "flex max-w-[760px] justify-end")}>
        <div
          className={cn(
            "relative border px-5 py-4 shadow-line",
            isUser ? "border-ink/80 bg-ink text-parchment" : "border-ink/10 bg-[#fffaf1]/78 text-ink backdrop-blur",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <p className="whitespace-pre-wrap text-[15px] leading-7">{message.content}</p>
            {!isUser && message.status !== "streaming" && (
              <button
                type="button"
                onClick={copy}
                className="shrink-0 rounded-full p-1.5 text-ink/45 opacity-0 outline-none transition hover:bg-ink/5 hover:text-ink focus:opacity-100 focus-visible:ring-2 focus-visible:ring-moss/40 group-hover:opacity-100"
                title="复制"
                aria-label="复制"
              >
                <Copy className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>

          {message.error && (
            <div className="mt-3 border border-tomato/30 bg-tomato/10 px-3 py-2 text-sm text-tomato">
              {message.error}
            </div>
          )}

          {!isUser && message.status === "streaming" && !message.steps?.length && (
            <div className="mt-3 inline-flex items-center gap-2 text-sm text-ink/50">
              <span className="inline-flex gap-1">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink/50" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink/50" style={{ animationDelay: "0.15s" }} />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink/50" style={{ animationDelay: "0.3s" }} />
              </span>
              正在思考…
            </div>
          )}

          {!isUser && <QueryMetaChips message={message} />}
          {!isUser && <PipelineFlow steps={message.steps} />}
          {!isUser && message.imageUrls && message.imageUrls.length > 0 && (
            <AnswerImages urls={message.imageUrls} />
          )}

          <div className={cn("mt-3 text-xs", isUser ? "text-parchment/55" : "text-ink/45")}>
            {formatTime(message.createdAt)}
          </div>
        </div>
      </div>

      {isUser && (
        <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-moss text-white">
          <UserRound className="h-4 w-4" aria-hidden="true" />
        </div>
      )}
    </article>
  );
}
