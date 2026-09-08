/**
 * 消息列表
 */
import type { ChatMessage } from "../../types/query";
import { MessageBubble } from "./MessageBubble";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6 lg:px-8">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}
