"use client";

import { useMoney } from "@/context/CurrencyContext";

/** A single line in an expandable statement/detail list: a title, a short meta
 *  line, and a signed amount. Shared by the per-card mini-statement
 *  (`CardStatus`) and the per-category budget detail (`BudgetProgress`). */
export function StatementRow({
  title,
  meta,
  amount,
  isInflow = false,
}: {
  title: string;
  meta: string;
  amount: string;
  isInflow?: boolean;
}) {
  const money = useMoney();
  return (
    <li className="flex items-start justify-between gap-3 text-sm">
      <div className="min-w-0">
        <p className="truncate text-ink">{title}</p>
        <p className="text-xs text-muted">{meta}</p>
      </div>
      <p
        className={`shrink-0 font-medium tabular-nums ${
          isInflow ? "text-positive" : "text-negative"
        }`}
      >
        {isInflow ? "+" : "−"}
        {money(amount)}
      </p>
    </li>
  );
}
