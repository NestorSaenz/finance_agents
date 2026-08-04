"use client";

import { categoryLabel, formatDayMonth, formatMoney } from "@/lib/format";
import type { Transaction } from "@/lib/types";

interface MovementsListProps {
  transactions: Transaction[];
}

/**
 * Chronological detail of every movement in the selected period. Complements the
 * category totals in the summary: here you can tell what each charge was (its
 * description, e.g. "Televisor (cuota 1/4)"), its category and when it happened.
 */
export function MovementsList({ transactions }: MovementsListProps) {
  if (transactions.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-center text-sm text-muted">
        Aún no hay movimientos en este período. Registra un gasto o ingreso desde el
        chat y aparecerá aquí.
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {transactions.map((tx) => {
        const isIncome = tx.transaction_type === "income";
        return (
          <li
            key={tx.id}
            className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface p-3"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-ink">{tx.description}</p>
              <p className="mt-0.5 text-xs text-muted">
                {categoryLabel(tx.category)} · {formatDayMonth(tx.transaction_date)}
              </p>
            </div>
            <p
              className={`shrink-0 text-sm font-semibold tabular-nums ${
                isIncome ? "text-positive" : "text-negative"
              }`}
            >
              {isIncome ? "+" : "−"}
              {formatMoney(tx.amount)}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
