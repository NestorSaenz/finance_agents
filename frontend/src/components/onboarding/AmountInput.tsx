"use client";

import { useLayoutEffect, useRef } from "react";

import {
  backspaceOverSeparator,
  digitsFromPaste,
  formatWithCaret,
  limitDigits,
} from "@/lib/moneyInput";

interface AmountInputProps {
  /** The amount as plain digits ("1500000"); shown with thousands separators. */
  value: string;
  onValueChange: (digits: string) => void;
  "aria-label": string;
  "aria-describedby"?: string;
  /** Lets a parent find this field (to move focus to it). */
  "data-cap-input"?: string;
  placeholder?: string;
  className?: string;
}

/** Text input for whole-number amounts: live thousands separators (max 10 digits),
 *  numeric keypad, and the caret stays on the digit being edited. */
export function AmountInput({
  value,
  onValueChange,
  placeholder,
  className = "",
  "aria-label": ariaLabel,
  "aria-describedby": describedBy,
  "data-cap-input": dataCapInput,
}: AmountInputProps) {
  const ref = useRef<HTMLInputElement>(null);
  const caret = useRef<number | null>(null);
  const shown = formatWithCaret(value, value.length).text;

  // Put the caret back after React re-renders the formatted text.
  useLayoutEffect(() => {
    if (caret.current !== null && ref.current && document.activeElement === ref.current) {
      ref.current.setSelectionRange(caret.current, caret.current);
    }
    caret.current = null;
  });

  function apply(raw: string, rawCaret: number) {
    // Extra digits are dropped; the caret never goes past what is kept.
    const digits = limitDigits(raw);
    const before = limitDigits(raw.slice(0, rawCaret)).length;
    const next = formatWithCaret(digits, before); // digits only: caret index = digit count
    caret.current = Math.min(next.caret, next.text.length);
    onValueChange(digits);
  }

  return (
    <input
      ref={ref}
      type="text"
      inputMode="numeric"
      autoComplete="off"
      placeholder={placeholder}
      aria-label={ariaLabel}
      aria-describedby={describedBy}
      data-cap-input={dataCapInput}
      value={shown}
      onKeyDown={(e) => {
        const input = e.currentTarget;
        if (e.key !== "Backspace" || input.selectionStart !== input.selectionEnd) return;
        const over = backspaceOverSeparator(input.value, input.selectionStart ?? 0);
        if (!over) return;
        e.preventDefault();
        apply(over.raw, over.caret);
      }}
      onChange={(e) => {
        apply(e.target.value, e.target.selectionStart ?? e.target.value.length);
      }}
      onPaste={(e) => {
        // Pasted amounts replace the field ("$1.500.000", "1,500,000", "1.500,50").
        e.preventDefault();
        const digits = limitDigits(digitsFromPaste(e.clipboardData.getData("text")));
        caret.current = formatWithCaret(digits, digits.length).text.length;
        onValueChange(digits);
      }}
      className={className}
    />
  );
}
