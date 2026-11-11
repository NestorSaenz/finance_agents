"use client";

import { useMoney } from "@/context/CurrencyContext";

export function IncomeGauge({
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
