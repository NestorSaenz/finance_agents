/** Helpers for amount inputs shown with thousands separators (whole numbers: COP). */

/** Only the digits of whatever was typed or pasted ("$1.500.000" -> "1500000"). */
export function digitsOnly(raw: string): string {
  return raw.replace(/\D/g, "");
}

/** "1500000" -> "1.500.000". Grouping is ALWAYS on (Intl "es" skips 4-digit numbers). */
export function formatAmountInput(raw: string): string {
  const digits = digitsOnly(raw).replace(/^0+(?=\d)/, "");
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** "1.500.000" -> 1500000. Empty / no digits -> 0. */
export function parseAmountInput(raw: string): number {
  const digits = digitsOnly(raw);
  return digits === "" ? 0 : Number(digits);
}

/**
 * Digits of a PASTED text: a trailing decimal part (",50" / ".5") is dropped, since
 * these amounts are whole numbers ("1.500,50" -> "1500"). Typing never uses this:
 * deleting one digit of "1.500" leaves "1.50", which must stay 150.
 */
export function digitsFromPaste(text: string): string {
  return digitsOnly(text.trim().replace(/[.,]\d{1,2}$/, ""));
}

/**
 * Re-format what the user just typed and keep the caret on the same digit.
 * `caret` is the position in `raw` (e.g. `selectionStart`).
 */
export function formatWithCaret(raw: string, caret: number): { text: string; caret: number } {
  const digitsBefore = digitsOnly(raw.slice(0, caret)).length;
  const text = formatAmountInput(raw);
  // Leading zeros dropped by formatting shift the count.
  const dropped = digitsOnly(raw).length - digitsOnly(text).length;
  let remaining = Math.max(0, digitsBefore - dropped);
  let position = 0;
  while (position < text.length && remaining > 0) {
    if (/\d/.test(text.charAt(position))) remaining -= 1;
    position += 1;
  }
  return { text, caret: position };
}

/** Most digits an amount may have (up to 9.999.999.999). */
export const MAX_AMOUNT_DIGITS = 10;

/** Keep only the first `max` digits of what was typed or pasted. */
export function limitDigits(raw: string, max: number = MAX_AMOUNT_DIGITS): string {
  return digitsOnly(raw).slice(0, max);
}

/**
 * Backspace pressed right after a thousands separator: remove the digit before it
 * (the separator itself is not editable). Returns the new raw text and caret, or
 * null when the key press does not apply.
 */
export function backspaceOverSeparator(
  text: string,
  caret: number,
): { raw: string; caret: number } | null {
  if (caret < 2 || text.charAt(caret - 1) !== ".") return null;
  return { raw: text.slice(0, caret - 2) + text.slice(caret), caret: caret - 2 };
}
