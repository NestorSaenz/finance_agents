import { forwardRef, type InputHTMLAttributes, useId } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, id, className = "", ...props },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const errorId = `${inputId}-error`;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium text-ink">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={`min-h-11 rounded-xl border bg-white px-3.5 text-sm text-ink placeholder:text-slate-400 transition-colors focus:border-brand-500 ${
          error ? "border-negative" : "border-line"
        } ${className}`}
        {...props}
      />
      {error && (
        <p id={errorId} className="text-sm text-negative">
          {error}
        </p>
      )}
    </div>
  );
});
