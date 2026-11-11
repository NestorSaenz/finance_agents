"use client";

import { useCurrency, useMoney } from "@/context/CurrencyContext";
import { summaryFigures } from "@/lib/summary";
import type {
  BudgetStatusList,
  CardPaymentsList,
  CreditCardStatusList,
  Goal,
  GoalMonthlyHistory,
  GoalPlanStatusList,
  Recurring,
  SpendingSummary,
  Transaction,
  UserProfile,
} from "@/lib/types";

import { CardPayments } from "./CardPayments";
import { CardStatus } from "./CardStatus";
import { CategorySpendingBars } from "./CategorySpendingBars";
import { GoalProgress } from "./GoalProgress";
import { PaymentSplit } from "./PaymentSplit";
import { CashFlowCard } from "./summary/CashFlowCard";
import { CategorySection } from "./summary/CategorySection";
import { IncomeGauge } from "./summary/IncomeGauge";
import { RecurringCard } from "./summary/RecurringCard";
import { Section } from "./summary/Section";
import { StatCard } from "./summary/StatCard";
import { SurplusCard } from "./summary/SurplusCard";

interface SummaryContentProps {
  summary: SpendingSummary;
  budget: BudgetStatusList | null;
  /** Expenses that IMPACT this period's budget (by=budget_date) — used to list
   *  what makes up each tope's "spent" on expand. Empty outside "este_mes". */
  budgetTransactions: Transaction[];
  profile: UserProfile | null;
  goals: Goal[];
  /** Gross amount set aside toward savings goals in the selected period. */
  goalSaved: number;
  /** Gross amount withdrawn from goals in the selected period. */
  goalWithdrawn: number;
  /** Free cash accumulated up to the selected month-end (carries over, no reset). */
  accumulatedSurplus: number;
  cards: CreditCardStatusList | null;
  payments: CardPaymentsList | null;
  /** This period's transactions — used to list each card's charges on expand. */
  transactions: Transaction[];
  /** Recurring templates (period-independent); read-only, managed via chat. */
  recurring: Recurring[];
  /** Goal plans vs contributed for the selected month (null = not loaded/failed). */
  planStatus?: GoalPlanStatusList | null;
  /** Month-by-month plan history, ending at the selected month. */
  goalHistory?: GoalMonthlyHistory | null;
  /** The selected period (e.g. "este_mes", "mes_pasado", "2026-06"). */
  period: string;
  /** Tapping a month in the plan history switches the panel to it. */
  onSelectMonth?: (month: string) => void;
}

/** The scrollable body of the dashboard: totals, gauge, and progress sections.
 *  Every figure comes from `summaryFigures` (lib/summary.ts); this only composes. */
export function SummaryContent({
  summary,
  budget,
  budgetTransactions,
  profile,
  goals,
  goalSaved,
  goalWithdrawn,
  accumulatedSurplus,
  cards,
  payments,
  transactions,
  recurring,
  period,
  planStatus = null,
  goalHistory = null,
  onSelectMonth,
}: SummaryContentProps) {
  const money = useMoney();
  const currency = useCurrency();
  const figures = summaryFigures({
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
  });
  const {
    activeGoals,
    historicalCards,
    expenses,
    referenceIncome,
    usesBaseFallback,
    income,
    spentOnGoals,
    totalSpent,
    goalsReturned,
    balance,
    pending,
    hasPending,
  } = figures;

  if (!figures.hasData) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-center text-sm text-muted">
        Aún no hay movimientos en este período. Registra un gasto o ingreso desde el
        chat y aparecerá aquí.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3">
        <StatCard label="Ingresos" value={income} tone="positive" />
        <StatCard
          label="Gastos"
          value={totalSpent}
          tone="negative"
          details={[
            ...(spentOnGoals > 0
              ? [`consumo ${money(expenses)}`, `+ apartado a metas ${money(spentOnGoals)}`]
              : []),
            ...(hasPending ? [`sin contar ${money(pending)} por aportar`] : []),
          ]}
        />
      </div>

      <div className="rounded-xl border border-line bg-surface p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">Balance</p>
        <p
          className={`mt-1 text-2xl font-semibold ${
            balance >= 0 ? "text-positive" : "text-negative"
          }`}
        >
          {money(balance)}
        </p>
        <p className="mt-2 text-xs text-muted">
          Ingresos menos gastos del mes
          {spentOnGoals > 0 ? " (incluye lo apartado a metas)" : ""}. Los cargos a
          crédito cuentan completos, aunque aún no los pagues — por eso puede diferir
          de tu caja real de abajo.
        </p>
        {goalsReturned > 0 && (
          <p className="mt-1 text-xs text-muted">
            Además volvieron {money(goalsReturned)} de tus metas (no es ingreso; ya está
            en tu caja final).
          </p>
        )}
      </div>

      {figures.hasCashFlow && (
        <CashFlowCard
          income={income}
          cashExpenses={figures.cashExpenses}
          cardPayments={figures.cardPayments}
          goalSaved={goalSaved}
          goalWithdrawn={goalWithdrawn}
          hasGoalFlow={figures.hasGoalFlow}
          afterSpending={figures.afterSpending}
          cashAvailable={figures.cashAvailable}
          pending={pending}
          hasPending={hasPending}
          afterPending={figures.afterPending}
          totalSpent={totalSpent}
          note={figures.cashFlowNote}
        />
      )}

      <SurplusCard accumulatedSurplus={accumulatedSurplus} />

      <RecurringCard recurring={recurring} />

      {income > 0 && (
        <IncomeGauge
          spent={totalSpent}
          income={income}
          note={
            [
              spentOnGoals > 0 ? `Incluye ${money(spentOnGoals)} apartados a metas.` : null,
              usesBaseFallback
                ? `Usando tu ingreso base ${money(referenceIncome)}. Registra o actualiza el de este mes para ajustarlo.`
                : null,
            ]
              .filter(Boolean)
              .join(" ") || undefined
          }
        />
      )}

      <CategorySection
        budget={budget}
        budgetTransactions={budgetTransactions}
        planStatus={planStatus}
        goalHistory={goalHistory}
        period={period}
        onSelectMonth={onSelectMonth}
        figures={figures}
      />

      {activeGoals.length > 0 && (
        <Section title="Metas de ahorro">
          <GoalProgress goals={activeGoals} />
        </Section>
      )}

      {cards && cards.cards.length > 0 && (
        <Section
          title="Tarjetas de crédito"
          subtitle={
            historicalCards
              ? "Deuda, disponible y pago reconstruidos a fin de ese mes."
              : "Estado a hoy."
          }
        >
          <CardStatus
            data={cards}
            transactions={transactions}
            payments={payments?.payments ?? []}
            period={period}
          />
        </Section>
      )}

      {payments && payments.payments.length > 0 && (
        <Section title="Pagos a tarjetas">
          <CardPayments data={payments} />
        </Section>
      )}

      <PaymentSplit
        credit={Number(summary.credit_expenses)}
        cash={Number(summary.cash_expenses)}
        totalExpenses={Number(summary.total_expenses)}
      />

      {summary.by_category.length > 0 && (
        <Section title="Gastos por categoría (consumo)">
          <CategorySpendingBars data={summary.by_category} />
        </Section>
      )}
    </div>
  );
}
