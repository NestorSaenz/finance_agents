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

/** One goal's history rows, oldest first, ending at `endMonth` (later months dropped). */
export function goalHistory(
  lines: ReadonlyArray<GoalMonthLine>,
  goalId: string,
  endMonth: string,
): GoalMonthLine[] {
  return lines
    .filter((l) => l.goal_id === goalId && l.month <= endMonth)
    .sort((a, b) => (a.month < b.month ? -1 : a.month > b.month ? 1 : 0));
}

export interface MonthState {
  kind: "sin_plan" | "cumplido" | "faltan";
  /** Fill 0–100 (0 without plan). */
  fill: number;
  /** What was still missing when the plan was not met. */
  missing: number;
}

/** Plan vs saved for one history month. A plan of 0 (or none) means "that month
 *  I did not plan". The effective plan (capped like the month block) is used when
 *  the backend sends it, falling back to `planned`. */
export function monthState(line: GoalMonthLine): MonthState {
  const effective = line.effective_planned ?? line.planned;
  const planned = effective === null ? 0 : Number(effective);
  if (line.planned === null || !(Number(line.planned) > 0) || !Number.isFinite(planned)) {
    return { kind: "sin_plan", fill: 0, missing: 0 };
  }
  const saved = Number(line.saved);
  if (saved >= planned) return { kind: "cumplido", fill: 100, missing: 0 };
  return {
    kind: "faltan",
    fill: Math.max(0, Math.min(100, (saved / planned) * 100)),
    missing: planned - saved,
  };
}
