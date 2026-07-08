"use client";

import { categoryLabel, formatMoney } from "@/lib/format";
import type { CategorySpending } from "@/lib/types";

/** Spending per category as lightweight CSS bars (no chart library).
 *
 * Bars scale relative to the largest category so the mix is easy to read; the
 * label shows the amount and its share of total expenses.
 */
export function CategorySpendingBars({ data }: { data: CategorySpending[] }) {
  if (data.length === 0) return null;

  const top = data.slice(0, 8);
  const maxAmount = Math.max(...top.map((c) => Number(c.amount)), 1);

  return (
    <div className="flex flex-col gap-3">
      {top.map((c) => {
        const amount = Number(c.amount);
        return (
          <div key={c.category}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="text-ink">{categoryLabel(c.category)}</span>
              <span className="text-muted">
                {formatMoney(amount)}{" "}
                <span className="text-xs">({c.percentage.toFixed(0)}%)</span>
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-brand-600 transition-all"
                style={{ width: `${(amount / maxAmount) * 100}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
