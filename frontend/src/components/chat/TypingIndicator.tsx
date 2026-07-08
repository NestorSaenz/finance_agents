export function TypingIndicator() {
  return (
    <span className="inline-flex items-center gap-1 py-1" aria-label="Escribiendo">
      <span className="h-2 w-2 animate-blink rounded-full bg-brand-400 [animation-delay:0ms]" />
      <span className="h-2 w-2 animate-blink rounded-full bg-brand-400 [animation-delay:200ms]" />
      <span className="h-2 w-2 animate-blink rounded-full bg-brand-400 [animation-delay:400ms]" />
    </span>
  );
}
