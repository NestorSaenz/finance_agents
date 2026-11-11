"use client";

import { useMoney } from "@/context/CurrencyContext";
import type { Recurring } from "@/lib/types";

/** Read-only "Recurrentes" card: fixed monthly incomes/expenses (managed via chat). */
export function RecurringCard({ recurring }: { recurring: Recurring[] }) {
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
