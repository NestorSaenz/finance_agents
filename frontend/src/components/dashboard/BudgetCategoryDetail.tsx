"use client";

import { useMemo } from "react";

import { useMoney } from "@/context/CurrencyContext";
import { categoryLabel, formatDayMonth } from "@/lib/format";
import type { Transaction } from "@/lib/types";

import { StatementRow } from "./StatementRow";

// Cap the visible rows so a busy "overall" (no-category) tope doesn't flood the
// panel. Safe to cap: the displayed total is always `spent`, never recomputed
// from the rows, so trimming the list never changes the number shown.
const MAX_ROWS = 12;

// If the listed rows' sum drifts from `spent` by more than this, something the
// UI can't fully explain happened (e.g. the fetch cap on very high volumes) —
// say so rather than silently show a number that disagrees with the bar.
const RECONCILE_TOLERANCE = 1;

interface BudgetCategoryDetailProps {
  id: string;
  label: string;
  /** The bar's own total — ALWAYS what's displayed here; rows only explain it,
   *  they never recompute it (see the reconciliation note below). */
  spent: string;
  rows: Transaction[];
}

/** The expandable detail for one budget/tope: the expenses that make up its
 *  "spent" this period, attributed the SAME way the number itself is (by
 *  budget_date, expense-only, excluding recurring bills) — so this list and
 *  the bar it belongs to can never silently disagree. */
export function BudgetCategoryDetail({
  id,
  label,
  spent,
  rows,
}: BudgetCategoryDetailProps) {
  const money = useMoney();
  const sorted = useMemo(
    () => [...rows].sort((a, b) => (a.budget_date < b.budget_date ? 1 : -1)),
    [rows],
  );
  const rowsTotal = sorted.reduce((sum, t) => sum + Number(t.amount), 0);
  const reconciles = Math.abs(rowsTotal - Number(spent)) <= RECONCILE_TOLERANCE;

  return (
    <div
      id={id}
      role="region"
      aria-label={`Movimientos de ${label}`}
      className="mt-3 border-t border-line pt-3"
    >
      <ul className="flex flex-col gap-2">
        {sorted.slice(0, MAX_ROWS).map((tx) => (
          <StatementRow
            key={tx.id}
            title={tx.description}
            meta={`${categoryLabel(tx.category)} · ${formatDayMonth(tx.transaction_date)}`}
            amount={tx.amount}
          />
        ))}
      </ul>
      {sorted.length > MAX_ROWS && (
        <p className="mt-2 text-xs text-muted">
          Mostrando los {MAX_ROWS} más recientes de {sorted.length}. Total: {money(spent)}.
        </p>
      )}
      {!reconciles && (
        <p className="mt-2 text-[11px] text-muted">
          No pudimos detallar todos los movimientos de este tope.
        </p>
      )}
    </div>
  );
}
