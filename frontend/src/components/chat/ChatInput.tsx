"use client";

import { ArrowUp, ImagePlus, X } from "lucide-react";
import { useEffect, useRef } from "react";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
  imageName: string | null;
  imagePreview: string | null;
  attachError: string | null;
  onAttach: (file: File) => void;
  onClearImage: () => void;
}

const MAX_HEIGHT = 160; // px — grow up to ~6 lines, then scroll.
const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp,application/pdf";

export function ChatInput({
  value,
  onChange,
  onSend,
  disabled,
  imageName,
  imagePreview,
  attachError,
  onAttach,
  onClearImage,
}: ChatInputProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Auto-grow to fit content, capped at MAX_HEIGHT.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  const canSend = (value.trim().length > 0 || imageName !== null) && !disabled;

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSend) onSend();
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) onAttach(file);
    event.target.value = ""; // allow re-selecting the same file
  }

  return (
    <div className="border-t border-line bg-surface/80 backdrop-blur">
      <div className="mx-auto w-full max-w-3xl px-4 py-3">
        {/* Attached-image chip with a thumbnail preview. */}
        {imageName && (
          <div className="mb-2 flex items-center gap-2 rounded-xl border border-line bg-white px-3 py-2 text-sm text-ink shadow-card">
            {imagePreview ? (
              // eslint-disable-next-line @next/next/no-img-element -- local data URL, not remote
              <img
                src={imagePreview}
                alt="Vista previa de la imagen adjunta"
                className="h-10 w-10 shrink-0 rounded-lg border border-line object-cover"
              />
            ) : (
              <ImagePlus className="h-5 w-5 shrink-0 text-brand-600" aria-hidden />
            )}
            <span className="flex-1 truncate">{imageName}</span>
            <button
              type="button"
              onClick={onClearImage}
              aria-label="Quitar imagen"
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-slate-100 hover:text-negative"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        )}

        <div className="flex items-end gap-2 rounded-2xl border border-line bg-white p-2 shadow-card focus-within:border-brand-400">
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={disabled}
            aria-label="Adjuntar imagen o PDF"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-muted transition-colors hover:bg-slate-100 hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ImagePlus className="h-5 w-5" aria-hidden />
          </button>
          <label htmlFor="chat-input" className="sr-only">
            Escribe tu mensaje
          </label>
          <textarea
            id="chat-input"
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Escribe tu mensaje…"
            className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-ink placeholder:text-slate-400 focus:outline-none"
          />
          <button
            onClick={onSend}
            disabled={!canSend}
            aria-label="Enviar mensaje"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowUp className="h-5 w-5" aria-hidden />
          </button>
        </div>
        {attachError ? (
          <p className="mt-1.5 px-1 text-center text-xs text-negative">{attachError}</p>
        ) : (
          <p className="mt-1.5 px-1 text-center text-xs text-slate-400">
            Safi puede cometer errores. Verifica la información importante.
          </p>
        )}
      </div>
    </div>
  );
}
