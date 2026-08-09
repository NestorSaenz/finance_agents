"use client";

import { formatMoney } from "@/lib/format";
import type {
  BudgetStatusList,
  CardPaymentsList,
  CreditCardStatusList,
  Goal,
  SpendingSummary,
  UserProfile,
} from "@/lib/types";

import { BudgetProgress } from "./BudgetProgress";
import { CardPayments } from "./CardPayments";
import { CardStatus } from "./CardStatus";
import { CategorySpendingBars } from "./CategorySpendingBars";
import { GoalProgress } from "./GoalProgress";
import { PaymentSplit } from "./PaymentSplit";

interface SummaryContentProps {
  summary: SpendingSummary;
  budget: BudgetStatusList | null;
  profile: UserProfile | null;
  goals: Goal[];
  cards: CreditCardStatusList | null;
  payments: CardPaymentsList | null;
  /** The selected period (e.g. "este_mes", "mes_pasado", "2026-06"). */
  period: string;
}

/** True when the selected period is a month earlier than the current one. */
function isPastMonth(period: string): boolean {
  if (period === "mes_pasado") return true;
  if (!/^\d{4}-\d{2}$/.test(period)) return false; // este_mes, todo → current
  const now = new Date();
  const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  return period < current;
}

/** The scrollable body of the dashboard: totals, gauge, and progress sections. */
export function SummaryContent({
  summary,
  budget,
  profile,
  goals,
  cards,
  payments,
  period,
}: SummaryContentProps) {
  const historicalCards = isPastMonth(period);
  const activeGoals = goals.filter(
    (g) => g.status === "active" || g.status === "completed",
  );
  const hasData =
    Number(summary.total_income) > 0 ||
    Number(summary.total_expenses) > 0 ||
    summary.by_category.length > 0 ||
    activeGoals.length > 0 ||
    (cards?.cards.length ?? 0) > 0;

  if (!hasData) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-center text-sm text-muted">
        Aún no hay movimientos en este período. Registra un gasto o ingreso desde el
        chat y aparecerá aquí.
      </div>
    );
  }

  const expenses = Number(summary.total_expenses);
  // Income the user logged as transactions this period.
  const registeredIncome = Number(summary.total_income);
  // Profile base salary — a FALLBACK, used only when this month has no logged
  // income (so a registered income replaces it, never stacks on top).
  const referenceIncome = Number(profile?.monthly_income ?? 0);
  const usesBaseFallback =
    registeredIncome === 0 && period === "este_mes" && referenceIncome > 0;
  const income = registeredIncome > 0 ? registeredIncome : usesBaseFallback ? referenceIncome : 0;
  const balance = income - expenses;

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3">
        <StatCard label="Ingresos" value={income} tone="positive" />
        <StatCard label="Gastos" value={summary.total_expenses} tone="negative" />
      </div>

      <div className="rounded-xl border border-line bg-surface p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">Balance</p>
        <p
          className={`mt-1 text-2xl font-semibold ${
            balance >= 0 ? "text-positive" : "text-negative"
          }`}
        >
          {formatMoney(balance)}
        </p>
      </div>

      {income > 0 && (
        <IncomeGauge
          spent={expenses}
          income={income}
          note={
            usesBaseFallback
              ? `Usando tu ingreso base ${formatMoney(referenceIncome)}. Registra o actualiza el de este mes para ajustarlo.`
              : undefined
          }
        />
      )}

      {budget && (
        <Section
          title="Cómo voy en cada categoría"
          subtitle="Incluye las compras a crédito según el mes en que las pagas."
        >
          <BudgetProgress data={budget} />
        </Section>
      )}

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
          <CardStatus data={cards} historical={historicalCards} />
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
        <Section title="Gastos por categoría">
          <CategorySpendingBars data={summary.by_category} />
        </Section>
      )}
    </div>
  );
}

function IncomeGauge({
  spent,
  income,
  note,
}: {
  spent: number;
  income: number;
  note?: string;
}) {
  const pct = income > 0 ? (spent / income) * 100 : 0;
  const over = pct >= 100;
  const near = pct >= 80;
  const barColor = over ? "bg-negative" : near ? "bg-amber-500" : "bg-brand-600";
  const pctColor = over ? "text-negative" : near ? "text-amber-600" : "text-muted";

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">
          Gastos vs ingresos
        </p>
        <p className={`text-sm font-semibold ${pctColor}`}>{pct.toFixed(0)}%</p>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <p className="mt-2 text-sm text-ink">
        <span className="font-semibold">{formatMoney(spent)}</span>
        <span className="text-muted"> de {formatMoney(income)}</span>
      </p>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {subtitle && <p className="mb-3 mt-0.5 text-xs text-muted">{subtitle}</p>}
      {!subtitle && <div className="mb-3" />}
      {children}
    </div>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: "positive" | "negative";
}) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p
        className={`mt-1 text-lg font-semibold ${
          tone === "positive" ? "text-positive" : "text-negative"
        }`}
      >
        {formatMoney(value)}
      </p>
    </div>
  );
}
