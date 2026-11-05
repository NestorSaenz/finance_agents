import type { BudgetStatusItem } from "@/lib/types";

/** Share of the user's base income that the budgets (topes) occupy. */
export interface BudgetIncomeShare {
  /** Σ monthly CATEGORY budgets (an overall budget is never added to this). */
  categoryTotal: number;
  /** categoryTotal as % of income, rounded to one decimal. */
  totalPct: number;
  /** The monthly overall (category-less) budget, shown apart from the total. */
  overall: { amount: number; pct: number } | null;
  /** % of income per monthly budget id (weekly/yearly budgets have no entry). */
  pctById: Map<string, number>;
}

function isMonthly(s: BudgetStatusItem): boolean {
  // Older payloads may omit period_type; the backend default is monthly.
  return (s.budget.period_type ?? "monthly") === "monthly";
}

/** % of `income`, rounded to one decimal (e.g. 88.5). */
function pctOf(amount: number, income: number): number {
  return Math.round((amount / income) * 1000) / 10;
}

/**
 * How much of the base monthly income the budgets take up. Returns null when
 * there is no usable income (missing, NaN or <= 0) so callers show nothing.
 * Computed client-side from the statuses — the backend's `total_budgeted` mixes
 * overall, weekly and yearly budgets and would double count.
 */
export function budgetIncomeShare(
  statuses: BudgetStatusItem[],
  income: number | null | undefined,
): BudgetIncomeShare | null {
  if (income == null || !Number.isFinite(income) || income <= 0) return null;

  let categoryTotal = 0;
  let overall: BudgetIncomeShare["overall"] = null;
  const pctById = new Map<string, number>();

  for (const s of statuses) {
    if (!isMonthly(s)) continue;
    const amount = Number(s.budget.amount);
    if (!Number.isFinite(amount)) continue;
    pctById.set(s.budget.id, pctOf(amount, income));
    if (s.budget.category) categoryTotal += amount;
    else overall ??= { amount, pct: pctOf(amount, income) }; // keep the first
  }

  return { categoryTotal, totalPct: pctOf(categoryTotal, income), overall, pctById };
}
