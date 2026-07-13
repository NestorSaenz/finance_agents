"use client";

import { useCallback, useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import { useRouter } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import type { ChatMessage } from "@/lib/types";

import { ChatInput } from "./ChatInput";
import { EmptyState } from "./EmptyState";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

const ERROR_MESSAGE =
  "Lo siento, tuve un problema procesando tu solicitud. Inténtalo de nuevo en un momento.";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
const MAX_IMAGE_BYTES = 8 * 1024 * 1024; // 8 MB

interface AttachedImage {
  base64: string; // without the data: prefix
  mime: string;
  name: string;
}

function newId(): string {
  return crypto.randomUUID();
}

/** Read a File into a base64 string (no data: prefix). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1] ?? "");
    reader.onerror = () => reject(new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

export interface ChatViewHandle {
  reset: () => void;
}

interface ChatViewProps {
  /** Called after each assistant reply, so the dashboard can refresh. */
  onDataChanged?: () => void;
}

export const ChatView = forwardRef<ChatViewHandle, ChatViewProps>(function ChatView(
  { onDataChanged },
  ref,
) {
  const router = useRouter();
  const { token, logout } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [image, setImage] = useState<AttachedImage | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    reset: () => {
      setMessages([]);
      setSessionId(null);
      setInput("");
      setImage(null);
      setAttachError(null);
    },
  }));

  const attachImage = useCallback(async (file: File) => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      setAttachError("Formato no válido. Usa JPG, PNG, WebP o PDF.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setAttachError("El archivo supera los 8 MB.");
      return;
    }
    try {
      const base64 = await fileToBase64(file);
      setImage({ base64, mime: file.type, name: file.name });
      setAttachError(null);
    } catch {
      setAttachError("No pude leer el archivo. Intenta con otro.");
    }
  }, []);

  // Keep the latest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const send = useCallback(async () => {
    const text = input.trim();
    if ((!text && !image) || sending) return;

    const attached = image;
    const userMessage: ChatMessage = {
      id: newId(),
      role: "user",
      content: text || (attached ? `📷 ${attached.name}` : ""),
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setImage(null);
    setAttachError(null);
    setSending(true);

    try {
      const res = await api.chat(
        {
          message: text,
          session_id: sessionId,
          image: attached?.base64,
          image_mime_type: attached?.mime,
        },
        token,
      );
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          content: res.response,
          createdAt: new Date().toISOString(),
        },
      ]);
      // A turn may have registered/updated a transaction → let the dashboard refresh.
      onDataChanged?.();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        router.replace("/login");
        return;
      }
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          content: ERROR_MESSAGE,
          createdAt: new Date().toISOString(),
        },
      ]);
    } finally {
      setSending(false);
    }
  }, [input, image, sending, sessionId, token, logout, router, onDataChanged]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {isEmpty ? (
        <EmptyState onPick={setInput} />
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {sending && (
              <div className="flex justify-start pl-11">
                <TypingIndicator />
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      )}

      <ChatInput
        value={input}
        onChange={setInput}
        onSend={send}
        disabled={sending}
        imageName={image?.name ?? null}
        imagePreview={
          image && image.mime.startsWith("image/")
            ? `data:${image.mime};base64,${image.base64}`
            : null
        }
        attachError={attachError}
        onAttach={attachImage}
        onClearImage={() => setImage(null)}
      />
    </div>
  );
});
