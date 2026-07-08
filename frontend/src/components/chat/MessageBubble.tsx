import { LineChart } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatMessage } from "@/lib/types";

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const time = formatTime(message.createdAt);

  return (
    <div
      className={`flex animate-fade-in-up gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && (
        <span
          className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-positive text-white"
          aria-hidden
        >
          <LineChart className="h-4 w-4" />
        </span>
      )}

      <div className={`flex max-w-[85%] flex-col sm:max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm ${
            isUser
              ? "rounded-br-md bg-brand-600 text-white"
              : "rounded-bl-md border border-line bg-surface text-ink shadow-card"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
          ) : (
            <div className="md">
              <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
            </div>
          )}
        </div>
        {time && (
          <span className="mt-1 px-1 text-[11px] text-muted" aria-hidden>
            {time}
          </span>
        )}
      </div>
    </div>
  );
}
