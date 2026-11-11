import { budgetIncomeShare, planIncomeShare } from "@/lib/budgets";
import type { BudgetIncomeShare, PlanIncomeShare } from "@/lib/budgets";
import {
  pendingSavingFor,
  planCurrencies,
  plannedSavingFor,
  resolveCurrency,
  selectedMonth,
  visiblePlans,
} from "@/lib/goalPlans";
import type {
  BudgetStatusList,
  CardPaymentsList,
  CreditCardStatusList,
  Goal,
  GoalMonthlyHistory,
  GoalPlanStatusList,
  SpendingSummary,
  UserProfile,
} from "@/lib/types";

export interface SummaryFiguresInput {
  summary: SpendingSummary;
  budget: BudgetStatusList | null;
  profile: UserProfile | null;
  goals: Goal[];
  /** Gross amount set aside toward savings goals in the selected period. */
  goalSaved: number;
  /** Gross amount withdrawn from goals in the selected period. */
  goalWithdrawn: number;
  cards: CreditCardStatusList | null;
  payments: CardPaymentsList | null;
  planStatus: GoalPlanStatusList | null;
  goalHistory: GoalMonthlyHistory | null;
  /** The selected period (e.g. "este_mes", "mes_pasado", "2026-06", "todo"). */
  period: string;
  /** The profile currency the dashboard shows money in. */
  currency: string;
  /** "Now" for resolving the viewed month; defaults to the real clock. */
  now?: Date;
}

/** Everything the summary derives from its inputs, computed once and purely. */
export interface SummaryFigures {
  activeGoals: Goal[];
  /** Past-month cards come back without a statement period. */
  historicalCards: boolean;
  /** False when the period has nothing at all to show. */
  hasData: boolean;

  /** Consumo: Σ expense transactions (Resumen "Gastos" before goals). */
  expenses: number;
  referenceIncome: number;
  usesBaseFallback: boolean;
  income: number;
  /** Aportes that count as gasto (goal_saved from the endpoint). */
  spentOnGoals: number;
  /** consumo + aportes (total_spent; older payloads: total_expenses). */
  totalSpent: number;
  /** Retiros reported by the endpoint (informational). */
  goalsReturned: number;
  balance: number;

  cashExpenses: number;
  cardPayments: number;
  hasGoalFlow: boolean;
  afterSpending: number;
  cashAvailable: number;
  cashFlowNote: string;

  /** Currency the plan lines are summarised in (may differ from the profile's). */
  planCurrency: string;
  /** What the month's plans still lack ("Este mes" only; never part of a total). */
  pending: number;
  hasPending: boolean;
  afterPending: number;
  hasCashFlow: boolean;

  hasPlans: boolean;
  plannedSaving: number;
  topesShare: BudgetIncomeShare | null;
  planShare: PlanIncomeShare | null;
  hasTopes: boolean;
  hasHistory: boolean;
  /** "YYYY-MM" the period points at. */
  viewedMonth: string;
}

/** Pure derivation of every figure the summary shows. No rounding, no formatting. */
export function summaryFigures(input: SummaryFiguresInput): SummaryFigures {
  const {
    summary,
    budget,
    profile,
    goals,
    goalSaved,
    goalWithdrawn,
    cards,
    payments,
    planStatus,
    goalHistory,
    period,
    currency,
    now,
  } = input;

  // Past-month cards come back without a statement period (see CardStatus), so
  // the subtitle follows the server's own live/past decision.
  const historicalCards =
    cards !== null && cards.cards.length > 0 && cards.cards.every((c) => c.statement_start === null);
  const activeGoals = goals.filter((g) => g.status === "active" || g.status === "completed");
  const hasData =
    Number(summary.total_income) > 0 ||
    Number(summary.total_expenses) > 0 ||
    summary.by_category.length > 0 ||
    activeGoals.length > 0 ||
    (cards?.cards.length ?? 0) > 0;

  const expenses = Number(summary.total_expenses);
  // Income the user logged as transactions this period.
  const registeredIncome = Number(summary.total_income);
  // Profile base salary — a FALLBACK, used only when this month has no logged
  // income (so a registered income replaces it, never stacks on top).
  const referenceIncome = Number(profile?.monthly_income ?? 0);
  const usesBaseFallback =
    registeredIncome === 0 && period === "este_mes" && referenceIncome > 0;
  const income = registeredIncome > 0 ? registeredIncome : usesBaseFallback ? referenceIncome : 0;
  // Gastos = consumo + what the user ALREADY set aside to goals (that money is no
  // longer available). Older payloads omit the new fields: then it is just consumo.
  const spentOnGoals = Number(summary.goal_saved ?? 0);
  const totalSpent = Number(summary.total_spent ?? summary.total_expenses);
  const goalsReturned = Number(summary.goal_withdrawn ?? 0);
  const balance = income - totalSpent;

  // Cash-flow lens: money that actually left the pocket this month = cash spent +
  // what was paid to cards (credit purchases count when you pay the card, not at
  // purchase). Answers "de mis ingresos, ¿cuánto me queda de verdad?".
  const cashExpenses = Number(summary.cash_expenses);
  const cardPayments = Number(payments?.total ?? 0);
  // Goal money is shown GROSS (never one net): what was set aside leaves the
  // disposable pool, what was withdrawn comes back. Neither is a gasto.
  const hasGoalFlow = goalSaved > 0 || goalWithdrawn > 0;
  // Two steps, so saving never reads as a loss: first what's left after money
  // that TRULY left the pocket (cash + card payments), then the final position
  // after the goal movements.
  const afterSpending = income - cashExpenses - cardPayments;
  const cashAvailable = afterSpending - goalSaved + goalWithdrawn;
  // What the month's plans still lack: informational, in "Este mes" only. It is
  // not a gasto until the aporte is registered, so it never enters a total.
  // Goals may be labelled with another currency than the profile's (single-
  // currency user): resolve which one the plan lines are summarised in.
  const planCurrency = resolveCurrency(planCurrencies(planStatus, goalHistory), currency);
  const pending = period === "este_mes" ? pendingSavingFor(planStatus, planCurrency) : 0;
  const hasPending = pending > 0;
  const hasCashFlow =
    income > 0 || cashExpenses > 0 || cardPayments > 0 || hasGoalFlow || hasPending;
  // Explain the bottom line in words. Aportes dated before the cutoff
  // (goal_spending_from) do not count as gasto, so they keep the old wording.
  const savedNote =
    spentOnGoals > 0
      ? "Lo apartado a metas cuenta en tus gastos del mes y sale de tu caja (sigue siendo tuyo)."
      : "Apartar para metas reduce tu caja del mes, pero no es gasto.";
  const cashFlowNote = !hasGoalFlow
    ? "Lo que te queda tras el efectivo y los pagos a tarjetas del mes."
    : goalSaved > 0 && goalWithdrawn > 0
      ? `${savedNote} Lo que retiraste de tus metas volvió a tu caja.`
      : goalSaved > 0
        ? savedNote
        : "Lo que retiraste de tus metas volvió a tu caja; no es un ingreso.";

  // Goal plans: a saving plan is NOT a gasto or a tope — it never touches the
  // totals above, only its own block and the "% de tu ingreso" lines.
  const hasPlans = visiblePlans(planStatus).length > 0;
  const plannedSaving = plannedSavingFor(planStatus, planCurrency);
  const topesShare = budgetIncomeShare(budget?.statuses ?? [], referenceIncome);
  const planShare = planIncomeShare(
    referenceIncome,
    plannedSaving,
    topesShare?.categoryTotal ?? 0,
  );
  const hasTopes = budget !== null && budget.statuses.length > 0;
  const afterPending = cashAvailable - pending;
  const hasHistory = (goalHistory?.lines.length ?? 0) > 0;
  const viewedMonth = selectedMonth(period, now);

  return {
    activeGoals,
    historicalCards,
    hasData,
    expenses,
    referenceIncome,
    usesBaseFallback,
    income,
    spentOnGoals,
    totalSpent,
    goalsReturned,
    balance,
    cashExpenses,
    cardPayments,
    hasGoalFlow,
    afterSpending,
    cashAvailable,
    cashFlowNote,
    planCurrency,
    pending,
    hasPending,
    afterPending,
    hasCashFlow,
    hasPlans,
    plannedSaving,
    topesShare,
    planShare,
    hasTopes,
    hasHistory,
    viewedMonth,
  };
}
