"use client";

import { useEffect, useMemo, useState } from "react";

import { categoryLabel, formatDayMonth, formatMoney } from "@/lib/format";
import type {
  CardPaymentsList,
  CreditCardStatusList,
  Transaction,
} from "@/lib/types";

interface MovementsListProps {
  transactions: Transaction[];
  cards: CreditCardStatusList | null;
  payments: CardPaymentsList | null;
}

/** "todas", "efectivo", or a specific card id. */
type MovementFilter = string;

const ALL: MovementFilter = "todas";
const CASH: MovementFilter = "efectivo";

/** A row in the list: either a logged transaction or a card payment (money paid
 *  toward a card, which leaves the pocket like cash). */
type Movement =
  | { kind: "tx"; date: string; tx: Transaction }
  | { kind: "payment"; date: string; id: string; cardName: string; amount: string };

/** Cash outflow: an explicitly-'efectivo' transaction, OR any card payment
 *  (paying a card is money out of pocket, so it counts under "Efectivo"). */
function isCashMovement(m: Movement): boolean {
  return m.kind === "payment" || m.tx.payment_method === "efectivo";
}

function matchesFilter(m: Movement, filter: MovementFilter): boolean {
  if (filter === ALL) return true;
  if (filter === CASH) return isCashMovement(m);
  // A specific card chip lists only that card's charges (payments are cash).
  return m.kind === "tx" && m.tx.card_id === filter;
}

/** Amount that left the pocket for this movement (0 for income). */
function outflow(m: Movement): number {
  if (m.kind === "payment") return Number(m.amount);
  return m.tx.transaction_type === "expense" ? Number(m.tx.amount) : 0;
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

/**
 * Chronological detail of every movement in the selected period — logged
 * transactions plus card payments — with a filter by source (all / cash / each
 * card). Card payments appear under "Efectivo" since paying a card is money out.
 */
export function MovementsList({ transactions, cards, payments }: MovementsListProps) {
  const [filter, setFilter] = useState<MovementFilter>(ALL);

  const cardNames = useMemo(
    () => new Map((cards?.cards ?? []).map((c) => [c.card.id, c.card.name])),
    [cards],
  );

  const movements = useMemo<Movement[]>(() => {
    const txs: Movement[] = transactions.map((tx) => ({
      kind: "tx",
      date: tx.transaction_date,
      tx,
    }));
    const pays: Movement[] = (payments?.payments ?? []).map((p, i) => ({
      kind: "payment",
      date: p.payment_date,
      id: `pay-${i}-${p.payment_date}`,
      cardName: p.card_name,
      amount: p.amount,
    }));
    return [...txs, ...pays].sort((a, b) =>
      a.date < b.date ? 1 : a.date > b.date ? -1 : 0,
    );
  }, [transactions, payments]);

  // Chips: only offer sources that actually appear in this period's movements.
  const chips = useMemo(() => {
    const hasCash = movements.some(isCashMovement);
    const cardOrder: { id: string; name: string }[] = [];
    const seen = new Set<string>();
    for (const m of movements) {
      if (m.kind === "tx" && m.tx.card_id && cardNames.has(m.tx.card_id) && !seen.has(m.tx.card_id)) {
        seen.add(m.tx.card_id);
        cardOrder.push({ id: m.tx.card_id, name: cardNames.get(m.tx.card_id) ?? "" });
      }
    }
    const items: { key: MovementFilter; label: string }[] = [{ key: ALL, label: "Todas" }];
    if (hasCash) items.push({ key: CASH, label: "💵 Efectivo" });
    for (const c of cardOrder) items.push({ key: c.id, label: `💳 ${c.name}` });
    return items;
  }, [movements, cardNames]);

  // Reset to "Todas" when the active chip disappears (e.g. switching to a month
  // where the selected card has no movements) — avoids a stuck empty state.
  useEffect(() => {
    if (!chips.some((chip) => chip.key === filter)) setFilter(ALL);
  }, [chips, filter]);

  const visible = useMemo(
    () => movements.filter((m) => matchesFilter(m, filter)),
    [movements, filter],
  );

  const filteredOutflow = useMemo(
    () => visible.reduce((sum, m) => sum + outflow(m), 0),
    [visible],
  );

  if (movements.length === 0) {
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
          {visible.length} movimiento(s) · {filter === CASH ? "salidas" : "gastado"}{" "}
          <span className="font-semibold text-ink">{formatMoney(filteredOutflow)}</span>
        </p>
      )}

      {visible.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-center text-sm text-muted">
          No hay movimientos con ese filtro en este período.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {visible.map((m) =>
            m.kind === "payment" ? (
              <li
                key={m.id}
                className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">
                    Pago a {m.cardName}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                    <span>Pago de tarjeta · {formatDayMonth(m.date)}</span>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-muted">
                      💳 Pago
                    </span>
                  </p>
                </div>
                <p className="shrink-0 text-sm font-semibold tabular-nums text-negative">
                  −{formatMoney(m.amount)}
                </p>
              </li>
            ) : (
              <MovementRow key={m.tx.id} tx={m.tx} cardNames={cardNames} />
            ),
          )}
        </ul>
      )}
    </div>
  );
}

function MovementRow({
  tx,
  cardNames,
}: {
  tx: Transaction;
  cardNames: Map<string, string>;
}) {
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
        {formatMoney(tx.amount)}
      </p>
    </li>
  );
}
