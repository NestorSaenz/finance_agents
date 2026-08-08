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
}

/** The scrollable body of the dashboard: totals, gauge, and progress sections. */
export function SummaryContent({
  summary,
  budget,
  profile,
  goals,
  cards,
  payments,
}: SummaryContentProps) {
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
  // Registered income for the period (income transactions the user logged).
  const additionalIncome = Number(summary.total_income);
  // Reference monthly income from the profile (a base salary the user doesn't
  // log as a transaction). Only meaningful for the current month.
  const referenceIncome = Number(profile?.monthly_income ?? 0);
  const hasReference = summary.period === "este_mes" && referenceIncome > 0;
  // Total income = base (reference) + what was registered this period. Additive,
  // so logging an extra income adds to the base instead of replacing it.
  const incomeBase = hasReference ? referenceIncome + additionalIncome : additionalIncome;
  const balance = incomeBase - expenses;

  return (
    <div className="flex flex-col gap-5">
      {hasReference && (
        <div className="rounded-xl border border-line bg-surface p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Ingreso base (referencia)
          </p>
          <p className="mt-1 text-lg font-semibold text-ink">
            {formatMoney(referenceIncome)}
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <StatCard
          label={hasReference ? "Ingresos adicionales" : "Ingresos"}
          value={summary.total_income}
          tone="positive"
        />
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

      {incomeBase > 0 && (
        <IncomeGauge
          spent={expenses}
          income={incomeBase}
          note={
            hasReference
              ? `Incluye tu ingreso base ${formatMoney(referenceIncome)} + ${formatMoney(
                  additionalIncome,
                )} registrados este mes.`
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
        <Section title="Tarjetas de crédito">
          <CardStatus data={cards} />
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
  value: string;
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
