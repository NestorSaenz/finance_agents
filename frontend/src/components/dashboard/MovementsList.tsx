"use client";

import { useEffect, useMemo, useState } from "react";

import { formatDayMonth } from "@/lib/format";
import {
  ALL,
  CASH,
  isCashMovement,
  matchesFilter,
  movementTotals,
  type Movement,
  type MovementFilter,
} from "@/lib/movements";
import type {
  CardPaymentsList,
  CreditCardStatusList,
  GoalContributionsList,
  Transaction,
} from "@/lib/types";

import { MovementRow, SummaryRow } from "./MovementRows";
import { MovementsTotals } from "./MovementsTotals";

interface MovementsListProps {
  transactions: Transaction[];
  cards: CreditCardStatusList | null;
  payments: CardPaymentsList | null;
  contributions: GoalContributionsList | null;
}

/**
 * Chronological detail of every movement in the selected period — logged
 * transactions, card payments, and goal contributions — with a filter by source
 * (all / cash / each card). Card payments and goal movements are listed under
 * "Efectivo"; goals are savings, so they are left out of its total (see
 * MovementsTotals).
 */
export function MovementsList({
  transactions,
  cards,
  payments,
  contributions,
}: MovementsListProps) {
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
    const contribs: Movement[] = (contributions?.contributions ?? []).map((c, i) => ({
      kind: "contribution",
      date: c.contribution_date,
      id: `contrib-${i}-${c.contribution_date}`,
      goalName: c.goal_name,
      amount: c.amount,
    }));
    return [...txs, ...pays, ...contribs].sort((a, b) =>
      a.date < b.date ? 1 : a.date > b.date ? -1 : 0,
    );
  }, [transactions, payments, contributions]);

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

  const totals = useMemo(() => movementTotals(visible), [visible]);

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

      <MovementsTotals
        mode={filter === ALL ? "all" : filter === CASH ? "cash" : "card"}
        count={visible.length}
        totals={totals}
      />

      {visible.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-center text-sm text-muted">
          No hay movimientos con ese filtro en este período.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {visible.map((m) => {
            if (m.kind === "payment") {
              return (
                <SummaryRow
                  key={m.id}
                  title={`Pago a ${m.cardName}`}
                  meta={`Pago de tarjeta · ${formatDayMonth(m.date)}`}
                  pillIcon="💳"
                  pillLabel="Pago"
                  amount={m.amount}
                />
              );
            }
            if (m.kind === "contribution") {
              // A negative contribution is a WITHDRAWAL: money leaves the goal and
              // returns to disponible, so it reads as an inflow (+), not an aporte.
              const value = Number(m.amount);
              if (value < 0) {
                return (
                  <SummaryRow
                    key={m.id}
                    title={`Retiro de ${m.goalName}`}
                    meta={`Retiro de meta · ${formatDayMonth(m.date)}`}
                    pillIcon="🎯"
                    pillLabel="Meta"
                    amount={Math.abs(value)}
                    isInflow
                  />
                );
              }
              return (
                <SummaryRow
                  key={m.id}
                  title={`Aporte a ${m.goalName}`}
                  meta={`Aporte a meta · ${formatDayMonth(m.date)}`}
                  pillIcon="🎯"
                  pillLabel="Meta"
                  amount={m.amount}
                />
              );
            }
            return <MovementRow key={m.tx.id} tx={m.tx} cardNames={cardNames} />;
          })}
        </ul>
      )}
    </div>
  );
}
