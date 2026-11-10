import { currentMonthKey } from "@/lib/format";
import type {
  GoalMonthLine,
  GoalPlanStatus,
  GoalPlanStatusList,
} from "@/lib/types";

/** Plan totals of ONE currency (currencies are never mixed). */
export interface PlanTotals {
  currency: string;
  /** Σ effective_planned (what the plans still needed). */
  planned: number;
  /** Σ gross contributions of the month. */
  saved: number;
}

/** Per-currency totals, sorted by currency code for a stable order. */
export function planTotals(list: GoalPlanStatusList): PlanTotals[] {
  return Object.keys(list.total_effective_planned)
    .sort()
    .map((currency) => ({
      currency,
      planned: Number(list.total_effective_planned[currency]),
      saved: Number(list.total_saved[currency] ?? 0),
    }));
}

/** The month's effective planned saving in `currency` (0 when none). */
export function plannedSavingFor(
  list: GoalPlanStatusList | null | undefined,
  currency: string,
): number {
  const value = Number(list?.total_effective_planned[currency] ?? 0);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

/** Fill of a plan bar, 0–100. Saving is never "over": it is capped, never red. */
export function planFill(status: GoalPlanStatus): number {
  const pct = Number.isFinite(status.percentage) ? status.percentage : 0;
  return Math.max(0, Math.min(100, pct));
}

/** Plans with something to show (effective plan > 0 or already met). */
export function visiblePlans(list: GoalPlanStatusList | null | undefined): GoalPlanStatus[] {
  return (list?.statuses ?? []).filter(
    (s) => Number(s.planned) > 0 || Number(s.effective_planned) > 0,
  );
}

const MONTH_NAMES = [
  "Ene", "Feb", "Mar", "Abr", "May", "Jun",
  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
];

/** "2026-11" -> "Nov 2026" (the raw string when malformed). */
export function monthLabel(month: string): string {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month);
  if (!match) return month;
  return `${MONTH_NAMES[Number(match[2]) - 1]} ${match[1]}`;
}

/** The month ("YYYY-MM") the dashboard period points at. */
export function selectedMonth(period: string, now: Date = new Date()): string {
  if (/^\d{4}-\d{2}$/.test(period)) return period;
  if (period === "mes_pasado") {
    return currentMonthKey(new Date(now.getFullYear(), now.getMonth() - 1, 1));
  }
  return currentMonthKey(now); // "este_mes" and "todo" end at the current month
}

/** `to` for GET /goals/monthly: undefined = the backend's current month. */
export function historyTo(period: string, now: Date = new Date()): string | undefined {
  return period === "este_mes" || period === "todo" ? undefined : selectedMonth(period, now);
}

/** What is still missing to reach the month's plans, in `currency` (>= 0).
 *  Informational: it never adds to any total until the aporte is registered. */
export function pendingSavingFor(
  list: GoalPlanStatusList | null | undefined,
  currency: string,
): number {
  let pending = 0;
  for (const s of visiblePlans(list)) {
    if (s.currency !== currency) continue;
    const remaining = Number(s.remaining);
    if (Number.isFinite(remaining) && remaining > 0) pending += remaining;
  }
  return pending;
}

/** One month of the plan history, for ONE currency. */
export interface MonthSummary {
  month: string;
  /** Σ effective plans of the goals planned that month. */
  planned: number;
  /** Σ gross saved by those goals. */
  saved: number;
  /** Goals that reached their plan. */
  met: number;
  /** Goals planned that month. */
  total: number;
}

/** Plan vs saved per month (oldest first). Months without a plan (null / 0) are
 *  left out; uses effective_planned when present, else planned. `endMonth` drops
 *  later months. */
export function monthSummaries(
  lines: ReadonlyArray<GoalMonthLine>,
  currency: string,
  endMonth?: string,
): MonthSummary[] {
  const byMonth = new Map<string, MonthSummary>();
  for (const l of lines) {
    if (l.currency !== currency || (endMonth && l.month > endMonth)) continue;
    const raw = l.effective_planned ?? l.planned;
    const planned = raw === null ? 0 : Number(raw);
    if (!(planned > 0) || !Number.isFinite(planned)) continue;
    const saved = Number(l.saved);
    const row = byMonth.get(l.month) ?? { month: l.month, planned: 0, saved: 0, met: 0, total: 0 };
    row.planned += planned;
    row.saved += Number.isFinite(saved) ? saved : 0;
    row.total += 1;
    if (saved >= planned) row.met += 1;
    byMonth.set(l.month, row);
  }
  return [...byMonth.values()].sort((a, b) => (a.month < b.month ? -1 : 1));
}
