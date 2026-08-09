"use client";

import { useEffect, useMemo, useState } from "react";

import { categoryLabel, formatDayMonth, formatMoney } from "@/lib/format";
import type { CreditCardStatusList, Transaction } from "@/lib/types";

interface MovementsListProps {
  transactions: Transaction[];
  cards: CreditCardStatusList | null;
}

/** "todas", "efectivo", or a specific card id. */
type MovementFilter = string;

const ALL: MovementFilter = "todas";
const CASH: MovementFilter = "efectivo";

/** A movement is cash only when explicitly tagged 'efectivo' — same rule the
 *  Resumen tab uses for its cash total, so both tabs agree. */
function isCash(tx: Transaction): boolean {
  return tx.payment_method === "efectivo";
}

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

/** The card/cash pill shown on each row (null when unknown). */
function methodBadge(
  tx: Transaction,
  cardNames: Map<string, string>,
): { icon: string; label: string } | null {
  const cardName = tx.card_id ? cardNames.get(tx.card_id) : undefined;
  if (cardName) return { icon: "💳", label: cardName };
  if (tx.payment_method === "credito") return { icon: "💳", label: "Crédito" };
  if (isCash(tx)) return { icon: "💵", label: "Efectivo" };
  return null;
}

function matchesFilter(tx: Transaction, filter: MovementFilter): boolean {
  if (filter === ALL) return true;
  if (filter === CASH) return isCash(tx);
  return tx.card_id === filter;
}

/**
 * Chronological detail of every movement in the selected period, with a filter
 * by payment source (all / cash / each card) and a per-row card label. Lets the
 * user answer "what did I pay with Nu?" or "what did I pay in cash?" in one place.
 */
export function MovementsList({ transactions, cards }: MovementsListProps) {
  const [filter, setFilter] = useState<MovementFilter>(ALL);

  const cardNames = useMemo(
    () => new Map((cards?.cards ?? []).map((c) => [c.card.id, c.card.name])),
    [cards],
  );

  // Chips: only offer sources that actually appear in this period's movements.
  const chips = useMemo(() => {
    const hasCash = transactions.some(isCash);
    const cardOrder: { id: string; name: string }[] = [];
    const seen = new Set<string>();
    for (const tx of transactions) {
      if (tx.card_id && cardNames.has(tx.card_id) && !seen.has(tx.card_id)) {
        seen.add(tx.card_id);
        cardOrder.push({ id: tx.card_id, name: cardNames.get(tx.card_id) ?? "" });
      }
    }
    const items: { key: MovementFilter; label: string }[] = [{ key: ALL, label: "Todas" }];
    if (hasCash) items.push({ key: CASH, label: "💵 Efectivo" });
    for (const c of cardOrder) items.push({ key: c.id, label: `💳 ${c.name}` });
    return items;
  }, [transactions, cardNames]);

  // Reset to "Todas" when the active chip disappears (e.g. switching to a month
  // where the selected card has no movements) — avoids a stuck empty state.
  useEffect(() => {
    if (!chips.some((chip) => chip.key === filter)) setFilter(ALL);
  }, [chips, filter]);

  const visible = useMemo(
    () => transactions.filter((tx) => matchesFilter(tx, filter)),
    [transactions, filter],
  );

  // Spent (expenses) within the current filter, for the summary line.
  const filteredExpense = useMemo(
    () =>
      visible
        .filter((tx) => tx.transaction_type === "expense")
        .reduce((sum, tx) => sum + Number(tx.amount), 0),
    [visible],
  );

  if (transactions.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-center text-sm text-muted">
        Aún no hay movimientos en este período. Registra un gasto o ingreso desde el
        chat y aparecerá aquí.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {chips.length > 1 && (
        <div
          className="flex gap-1.5 overflow-x-auto pb-1"
          role="group"
          aria-label="Filtrar movimientos por fuente de pago"
        >
          {chips.map((chip) => (
            <button
              key={chip.key}
              aria-pressed={filter === chip.key}
              onClick={() => setFilter(chip.key)}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                filter === chip.key
                  ? "bg-brand-600 text-white"
                  : "bg-slate-100 text-muted hover:text-ink"
              }`}
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {filter !== ALL && (
        <p className="text-xs text-muted">
          {visible.length} movimiento(s) · gastado{" "}
          <span className="font-semibold text-ink">{formatMoney(filteredExpense)}</span>
        </p>
      )}

      {visible.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-center text-sm text-muted">
          No hay movimientos con ese filtro en este período.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {visible.map((tx) => {
            const isIncome = tx.transaction_type === "income";
            const impact = impactMonth(tx);
            const badge = methodBadge(tx, cardNames);
            return (
              <li
                key={tx.id}
                className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface p-3"
              >
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
                  {formatMoney(tx.amount)}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
