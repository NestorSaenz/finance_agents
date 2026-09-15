"use client";

import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";

import { useMoney } from "@/context/CurrencyContext";
import { categoryLabel } from "@/lib/format";
import type { BudgetStatusItem, BudgetStatusList, Transaction } from "@/lib/types";

import { BudgetCategoryDetail } from "./BudgetCategoryDetail";

/** Colour a progress bar by spending vs the limit.
 *
 * Only being OVER the tope (> 100%) turns it red; at or under the tope it stays
 * the normal tone. A fixed expense that sits exactly at its cap every month
 * (e.g. a recurring one) shouldn't scream red when nothing was actually exceeded.
 */
function toneFor(pct: number): { bar: string; text: string } {
  if (pct > 100) return { bar: "bg-negative", text: "text-negative" };
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

interface BudgetProgressProps {
  data: BudgetStatusList;
  /** Expenses that impact this period's budget (fetched with by=budget_date —
   *  the SAME attribution rule "spent" itself uses: expense-only, excludes
   *  recurring bills). Grouped per category so an expand explains the number
   *  shown, never recomputes it. Empty outside "este_mes" (budgets are current-
   *  period only, so there's nothing to expand there anyway). */
  transactions: Transaction[];
}

export function BudgetProgress({ data, transactions }: BudgetProgressProps) {
  // One category's detail expands at a time (mirrors CardStatus's accordion).
  const [openId, setOpenId] = useState<string | null>(null);

  // Group budget-attributed expense rows by category ONCE, so each row just
  // reads its slice. A budget with no single category (category: null, an
  // "overall" tope) gets every row — sum_expenses with p_category IS NULL
  // sums everything the same way.
  const byCategory = useMemo(() => {
    const map = new Map<string, Transaction[]>();
    for (const tx of transactions) {
      if (tx.transaction_type !== "expense" || tx.recurring_id) continue;
      const bucket = map.get(tx.category);
      if (bucket) bucket.push(tx);
      else map.set(tx.category, [tx]);
    }
    return map;
  }, [transactions]);

  const allExpenseRows = useMemo(
    () => transactions.filter((t) => t.transaction_type === "expense" && !t.recurring_id),
    [transactions],
  );

  if (data.statuses.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-surface p-4 text-center text-sm text-muted">
        Aún no tienes topes definidos. Crea uno diciéndole a Safi, p. ej.
        “ponme un tope de 3000 en restaurantes”.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {data.statuses.map((s) => (
        <BudgetRow
          key={s.budget.id}
          status={s}
          rows={s.budget.category ? (byCategory.get(s.budget.category) ?? []) : allExpenseRows}
          isOpen={openId === s.budget.id}
          onToggle={() =>
            setOpenId((id) => (id === s.budget.id ? null : s.budget.id))
          }
        />
      ))}
    </div>
  );
}

function BudgetRow({
  status: s,
  rows,
  isOpen,
  onToggle,
}: {
  status: BudgetStatusItem;
  rows: Transaction[];
  isOpen: boolean;
  onToggle: () => void;
}) {
  const money = useMoney();
  const pct = s.percentage;
  const tone = toneFor(pct);
  const label = s.budget.category ? categoryLabel(s.budget.category) : s.budget.name;
  const hasDetail = rows.length > 0;
  const regionId = `budget-detail-${s.budget.id}`;

  // Disclosure toggle carries ONLY phrasing content (label + spent/limit +
  // chevron); the progress bar stays static outside the button, as in CardStatus.
  const header = (
    <>
      <span className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-ink">{label}</span>
        {hasDetail && (
          <ChevronDown
            className={`h-4 w-4 shrink-0 text-muted transition-transform motion-reduce:transition-none ${
              isOpen ? "rotate-180" : ""
            }`}
            aria-hidden
          />
        )}
      </span>
      <span className={`shrink-0 ${tone.text}`}>
        {money(s.spent)} <span className="text-muted">/ {money(s.budget.amount)}</span>
      </span>
    </>
  );

  return (
    <div>
      {hasDetail ? (
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isOpen}
          // Only reference the region while it's actually in the DOM (rendered on open).
          aria-controls={isOpen ? regionId : undefined}
          aria-label={`Ver movimientos de ${label}`}
          className="-my-1 flex w-full items-baseline justify-between gap-2 rounded-md py-1 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
        >
          {header}
        </button>
      ) : (
        <div className="flex items-baseline justify-between gap-2 text-sm">{header}</div>
      )}

      <div className="mt-1">
        <Bar pct={pct} className={tone.bar} />
      </div>

      {hasDetail && isOpen && (
        <BudgetCategoryDetail id={regionId} label={label} spent={s.spent} rows={rows} />
      )}
    </div>
  );
}
