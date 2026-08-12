"use client";

import { useMoney } from "@/context/CurrencyContext";
import { categoryLabel } from "@/lib/format";
import type { BudgetStatusList } from "@/lib/types";

/** Colour a progress bar by how close spending is to the limit. */
function toneFor(pct: number): { bar: string; text: string } {
  if (pct >= 100) return { bar: "bg-negative", text: "text-negative" };
  if (pct >= 80) return { bar: "bg-amber-500", text: "text-amber-600" };
  return { bar: "bg-brand-600", text: "text-muted" };
}

function Bar({ pct, className }: { pct: number; className: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div
        className={`h-full rounded-full transition-all ${className}`}
        style={{ width: `${Math.min(pct, 100)}%` }}
      />
    </div>
  );
}

export function BudgetProgress({ data }: { data: BudgetStatusList }) {
  const money = useMoney();
  if (data.statuses.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-surface p-4 text-center text-sm text-muted">
        Aún no tienes topes definidos. Crea uno diciéndole a Safi, p. ej.
        “ponme un tope de 3000 en restaurantes”.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Per-category budgets */}
      <div className="flex flex-col gap-3">
        {data.statuses.map((s) => {
          const pct = s.percentage;
          const tone = toneFor(pct);
          const label = s.budget.category
            ? categoryLabel(s.budget.category)
            : s.budget.name;
          return (
            <div key={s.budget.id}>
              <div className="mb-1 flex items-baseline justify-between text-sm">
                <span className="text-ink">{label}</span>
                <span className={tone.text}>
                  {money(s.spent)}{" "}
                  <span className="text-muted">/ {money(s.budget.amount)}</span>
                </span>
              </div>
              <Bar pct={pct} className={tone.bar} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
