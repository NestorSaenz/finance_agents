"use client";

import { useMoney } from "@/context/CurrencyContext";
import type {
  BudgetStatusList,
  CardPaymentsList,
  CreditCardStatusList,
  Goal,
  Recurring,
  SpendingSummary,
  Transaction,
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
  /** Total set aside toward savings goals in the selected period. */
  goalContributions: number;
  /** Free cash accumulated up to the selected month-end (carries over, no reset). */
  accumulatedSurplus: number;
  cards: CreditCardStatusList | null;
  payments: CardPaymentsList | null;
  /** This period's transactions — used to list each card's charges on expand. */
  transactions: Transaction[];
  /** Recurring templates (period-independent); read-only, managed via chat. */
  recurring: Recurring[];
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
  goalContributions,
  accumulatedSurplus,
  cards,
  payments,
  transactions,
  recurring,
  period,
}: SummaryContentProps) {
  const money = useMoney();
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

  // Cash-flow lens: money that actually left the pocket this month = cash spent +
  // what was paid to cards (credit purchases count when you pay the card, not at
  // purchase). Answers "de mis ingresos, ¿cuánto me queda de verdad?".
  const cashExpenses = Number(summary.cash_expenses);
  const cardPayments = Number(payments?.total ?? 0);
  // Money set aside to savings goals this month also leaves the disposable pool.
  const goalContribs = goalContributions;
  // Two steps, so saving never reads as a loss: first what's left after money
  // that TRULY left the pocket (cash + card payments), then the final position
  // after choosing to move some into goals.
  const afterSpending = income - cashExpenses - cardPayments;
  const cashAvailable = afterSpending - goalContribs;
  const hasCashFlow =
    income > 0 || cashExpenses > 0 || cardPayments > 0 || goalContribs !== 0;
  // Explain the bottom line in words — saving is not spending.
  const cashFlowNote =
    goalContribs > 0
      ? cashAvailable >= 0
        ? `Te sobró incluso después de guardar ${money(goalContribs)} en metas. Aportar a metas es ahorro, no gasto.`
        : `Aportar a metas es ahorro, no gasto: este mes guardaste ${money(Math.abs(cashAvailable))} más de lo que te quedó disponible.`
      : goalContribs < 0
        ? `Incluye ${money(Math.abs(goalContribs))} que retiraste de tus metas y volvió a tu bolsillo.`
        : "Lo que te queda tras el efectivo y los pagos a tarjetas del mes.";

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
          {money(balance)}
        </p>
        <p className="mt-2 text-xs text-muted">
          Ingresos menos gastos del mes. Los cargos a crédito cuentan completos,
          aunque aún no los pagues — por eso puede diferir de tu caja real de abajo.
        </p>
      </div>

      {hasCashFlow && (
        <div className="rounded-xl border border-line bg-surface p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Flujo de caja
          </p>
          <dl className="mt-2 flex flex-col gap-1 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-muted">Ingresos</dt>
              <dd className="tabular-nums text-positive">{money(income)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted">Efectivo</dt>
              <dd className="tabular-nums text-negative">−{money(cashExpenses)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted">Pagos a tarjetas</dt>
              <dd className="tabular-nums text-negative">−{money(cardPayments)}</dd>
            </div>

            {/* Subtotal after money that ACTUALLY left the pocket. When there are
                no goal movements this is already the bottom line. */}
            <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5">
              <dt className="font-medium text-ink">
                {goalContribs !== 0
                  ? afterSpending >= 0
                    ? "Te sobró"
                    : "Te faltó"
                  : "Disponible del mes"}
              </dt>
              <dd
                className={`font-semibold tabular-nums ${
                  afterSpending >= 0 ? "text-positive" : "text-negative"
                }`}
              >
                {money(afterSpending)}
              </dd>
            </div>

            {/* Saving is NOT spending: goal money apart in a neutral tone, then
                the final cash position after choosing to save. */}
            {goalContribs !== 0 && (
              <>
                <div className="flex items-center justify-between">
                  <dt className="text-muted">
                    {goalContribs >= 0 ? "Guardado en metas" : "Retirado de metas"}
                  </dt>
                  <dd
                    className={`tabular-nums ${
                      goalContribs >= 0 ? "text-brand-600" : "text-positive"
                    }`}
                  >
                    {goalContribs >= 0 ? "−" : "+"}
                    {money(Math.abs(goalContribs))}
                  </dd>
                </div>
                <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5">
                  <dt className="font-medium text-ink">Caja final del mes</dt>
                  <dd
                    className={`font-semibold tabular-nums ${
                      cashAvailable >= 0 ? "text-positive" : "text-amber-600"
                    }`}
                  >
                    {money(cashAvailable)}
                  </dd>
                </div>
              </>
            )}
          </dl>
          <p className="mt-2 text-xs text-muted">{cashFlowNote}</p>
        </div>
      )}

      <div className="rounded-xl border border-line bg-surface p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">
          Excedente acumulado
        </p>
        <p
          className={`mt-1 text-2xl font-semibold ${
            accumulatedSurplus >= 0 ? "text-positive" : "text-negative"
          }`}
        >
          {money(accumulatedSurplus)}
        </p>
        <p className="mt-2 text-xs text-muted">
          Tu plata libre acumulada, mes a mes. Baja cuando gastas o aportas a metas.
        </p>
      </div>

      <RecurringCard recurring={recurring} />

      {income > 0 && (
        <IncomeGauge
          spent={expenses}
          income={income}
          note={
            usesBaseFallback
              ? `Usando tu ingreso base ${money(referenceIncome)}. Registra o actualiza el de este mes para ajustarlo.`
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
          <CardStatus
            data={cards}
            historical={historicalCards}
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
        <Section title="Gastos por categoría">
          <CategorySpendingBars data={summary.by_category} />
        </Section>
      )}
    </div>
  );
}

/** Read-only "Recurrentes" card: fixed monthly incomes/expenses (managed via chat). */
function RecurringCard({ recurring }: { recurring: Recurring[] }) {
  const money = useMoney();
  if (recurring.length === 0) return null; // empty → render nothing, no empty box

  const incomes = recurring.filter((r) => r.transaction_type === "income");
  const expenses = recurring.filter((r) => r.transaction_type === "expense");
  const sumActive = (items: Recurring[]): number =>
    items.reduce((acc, r) => (r.active ? acc + Number(r.amount) : acc), 0);
  const netMonthly = sumActive(incomes) - sumActive(expenses);

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">
        Recurrentes
      </p>

      <div className="mt-3 flex flex-col gap-4">
        {incomes.length > 0 && (
          <RecurringGroup title="Ingresos fijos" items={incomes} sign="+" tone="positive" />
        )}
        {expenses.length > 0 && (
          <RecurringGroup title="Gastos fijos" items={expenses} sign="−" tone="negative" />
        )}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-line pt-2">
        <span className="text-sm font-medium text-ink">Neto fijo mensual</span>
        <span
          className={`text-sm font-semibold tabular-nums ${
            netMonthly >= 0 ? "text-positive" : "text-negative"
          }`}
        >
          {money(netMonthly)}
        </span>
      </div>

      <p className="mt-2 text-xs text-muted">
        Se registran solos cada mes. Gestiónalos desde el chat 💬
      </p>
    </div>
  );
}

function RecurringGroup({
  title,
  items,
  sign,
  tone,
}: {
  title: string;
  items: Recurring[];
  sign: "+" | "−";
  tone: "positive" | "negative";
}) {
  const money = useMoney();
  const amountColor = tone === "positive" ? "text-positive" : "text-negative";
  return (
    <div>
      <p className="text-xs font-medium text-muted">{title}</p>
      <ul className="mt-1 flex flex-col gap-1.5">
        {items.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-2 text-sm">
            <span
              className={`flex min-w-0 items-center gap-1.5 ${
                r.active ? "text-ink" : "text-muted"
              }`}
            >
              <span className="truncate">{r.description}</span>
              <span className="shrink-0 text-muted">· día {r.day_of_month}</span>
              {!r.active && (
                <span className="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-muted">
                  pausado
                </span>
              )}
            </span>
            <span
              className={`shrink-0 tabular-nums ${r.active ? amountColor : "text-muted"}`}
            >
              {sign}
              {money(r.amount)}
            </span>
          </li>
        ))}
      </ul>
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
  const money = useMoney();
  const pct = income > 0 ? (spent / income) * 100 : 0;
  // Only red once you actually spend MORE than you earn (> 100%); at or under it
  // stays neutral, so fixed/recurring expenses sitting near 100% don't read as an
  // alarm when nothing was exceeded.
  const over = pct > 100;
  const barColor = over ? "bg-negative" : "bg-brand-600";
  const pctColor = over ? "text-negative" : "text-muted";

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
        <span className="font-semibold">{money(spent)}</span>
        <span className="text-muted"> de {money(income)}</span>
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
  const money = useMoney();
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p
        className={`mt-1 text-lg font-semibold ${
          tone === "positive" ? "text-positive" : "text-negative"
        }`}
      >
        {money(value)}
      </p>
    </div>
  );
}
