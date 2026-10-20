"use client";

import { useMoney } from "@/context/CurrencyContext";
import { categoryLabel, formatDayMonth } from "@/lib/format";
import type { Transaction } from "@/lib/types";

/** Month label (e.g. "sep") of a credit charge's budget/impact month, when it
 *  differs from the purchase month; otherwise null. */
function impactMonth(tx: Transaction): string | null {
  if (!tx.budget_date || tx.budget_date.slice(0, 7) === tx.transaction_date.slice(0, 7)) {
    return null;
  }
  const d = new Date(`${tx.budget_date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("es-ES", { month: "short" });
}

/** The card/cash pill shown on a transaction row (null when unknown). */
function methodBadge(
  tx: Transaction,
  cardNames: Map<string, string>,
): { icon: string; label: string } | null {
  const cardName = tx.card_id ? cardNames.get(tx.card_id) : undefined;
  if (cardName) return { icon: "💳", label: cardName };
  if (tx.payment_method === "credito") return { icon: "💳", label: "Crédito" };
  if (tx.payment_method === "efectivo") return { icon: "💵", label: "Efectivo" };
  return null;
}

/** A summary row shared by card payments and goal contributions/withdrawals: a
 *  title, a meta line with a distinct pill, and the amount. Outflows (payments,
 *  aportes) show as a negative amount; an inflow (a goal withdrawal, money back to
 *  disponible) shows as a positive amount in the positive tone. */
export function SummaryRow({
  title,
  meta,
  pillIcon,
  pillLabel,
  amount,
  isInflow = false,
}: {
  title: string;
  meta: string;
  pillIcon: string;
  pillLabel: string;
  amount: string | number;
  isInflow?: boolean;
}) {
  const money = useMoney();
  return (
    <li className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface p-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink">{title}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
          <span>{meta}</span>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-muted">
            {pillIcon} {pillLabel}
          </span>
        </p>
      </div>
      <p
        className={`shrink-0 text-sm font-semibold tabular-nums ${
          isInflow ? "text-positive" : "text-negative"
        }`}
      >
        {isInflow ? "+" : "−"}
        {money(amount)}
      </p>
    </li>
  );
}

export function MovementRow({
  tx,
  cardNames,
}: {
  tx: Transaction;
  cardNames: Map<string, string>;
}) {
  const money = useMoney();
  const isIncome = tx.transaction_type === "income";
  const impact = impactMonth(tx);
  const badge = methodBadge(tx, cardNames);
  return (
    <li className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface p-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink">{tx.description}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
          <span>
            {categoryLabel(tx.category)} · {formatDayMonth(tx.transaction_date)}
          </span>
          {badge && (
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-muted">
              {badge.icon} {badge.label}
            </span>
          )}
          {impact && (
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-muted">
              🗓 impacta {impact}
            </span>
          )}
        </p>
      </div>
      <p
        className={`shrink-0 text-sm font-semibold tabular-nums ${
          isIncome ? "text-positive" : "text-negative"
        }`}
      >
        {isIncome ? "+" : "−"}
        {money(tx.amount)}
      </p>
    </li>
  );
}
