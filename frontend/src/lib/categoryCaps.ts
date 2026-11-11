import { categoryLabel } from "@/lib/format";
import { parseAmountInput } from "@/lib/moneyInput";

/** Lowercase and accent-free, for matching ("Jardiner\u00eda" ~ "jardineria"). */
export function normalizeText(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

/** A user-typed category as stored: trimmed, lowercase, single spaces. */
export function normalizeCategory(raw: string): string {
  return raw.trim().toLowerCase().replace(/\s+/g, " ");
}

export interface CapsSummary {
  /** Categories chosen (with or without an amount yet). */
  count: number;
  /** Σ of the amounts typed. */
  total: number;
  /** total as % of income, one decimal; null without a usable income. */
  pct: number | null;
}

export function capsSummary(
  selected: string[],
  caps: Record<string, string>,
  income: number | null | undefined,
): CapsSummary {
  const total = selected.reduce((sum, c) => sum + parseAmountInput(caps[c] ?? ""), 0);
  const pct =
    income != null && Number.isFinite(income) && income > 0
      ? Math.round((total / income) * 1000) / 10
      : null;
  return { count: selected.length, total, pct };
}

/** % of income one cap takes (one decimal); null without a usable income. */
export function capPct(amount: number, income: number | null | undefined): number | null {
  if (income == null || !Number.isFinite(income) || income <= 0) return null;
  return Math.round((amount / income) * 1000) / 10;
}

/** Categories matching `query` (by label or slug), not already chosen. */
export function filterCategories(query: string, all: string[], selected: string[]): string[] {
  const q = normalizeText(query);
  return all.filter(
    (c) =>
      !selected.includes(c) &&
      (q === "" || normalizeText(categoryLabel(c)).includes(q) || normalizeText(c).includes(q)),
  );
}

/** True when `query` is text that matches no existing category exactly. */
export function canCreate(query: string, all: string[]): boolean {
  const q = normalizeText(query);
  if (q === "") return false;
  return !all.some((c) => normalizeText(c) === q || normalizeText(categoryLabel(c)) === q);
}
