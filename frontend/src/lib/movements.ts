import type { Transaction } from "@/lib/types";

/** "todas", "efectivo", or a specific card id. */
export type MovementFilter = string;

export const ALL: MovementFilter = "todas";
export const CASH: MovementFilter = "efectivo";

/** A row in the movements list: a logged transaction, a card payment (money paid
 *  toward a card), or a goal contribution (aporte/retiro). Payments and goal
 *  movements are listed under "Efectivo"; only payments count as cash outflow —
 *  goals are savings. */
export type Movement =
  | { kind: "tx"; date: string; tx: Transaction }
  | { kind: "payment"; date: string; id: string; cardName: string; amount: string }
  | { kind: "contribution"; date: string; id: string; goalName: string; amount: string };

/** Cash transaction — mirrors the backend spending summary: explicitly 'efectivo',
 *  or untagged and not linked to a card. Credit / card-linked charges are not cash. */
export function isCashTx(tx: Transaction): boolean {
  return tx.payment_method === "efectivo" || (tx.payment_method == null && !tx.card_id);
}

/** Listed under the "Efectivo" chip: cash transactions, card payments, and goal
 *  movements (the latter are listed there but are savings, not money spent). */
export function isCashMovement(m: Movement): boolean {
  if (m.kind === "payment" || m.kind === "contribution") return true;
  return isCashTx(m.tx);
}

export function matchesFilter(m: Movement, filter: MovementFilter): boolean {
  if (filter === ALL) return true;
  if (filter === CASH) return isCashMovement(m);
  // A specific card chip lists only that card's charges (payments are cash).
  return m.kind === "tx" && m.tx.card_id === filter;
}

/** Purchase amount of an expense transaction (any payment method); 0 for income,
 *  card payments and goal movements. Σ over all rows = the Resumen "Gastos". */
export function expenseAmount(m: Movement): number {
  return m.kind === "tx" && m.tx.transaction_type === "expense" ? Number(m.tx.amount) : 0;
}

export interface MovementTotals {
  /** Σ expense transactions (any payment method). */
  expenses: number;
  /** Σ card payments. */
  paid: number;
  /** Gross goal aportes (positive contributions). */
  saved: number;
  /** Gross goal retiros (|negative contributions|). */
  withdrawn: number;
}

/** Totals over a list of movements. Goal movements never count as expense. */
export function movementTotals(list: Movement[]): MovementTotals {
  const totals: MovementTotals = { expenses: 0, paid: 0, saved: 0, withdrawn: 0 };
  for (const m of list) {
    if (m.kind === "payment") totals.paid += Number(m.amount);
    else if (m.kind === "contribution") {
      const value = Number(m.amount);
      if (value > 0) totals.saved += value;
      else totals.withdrawn += Math.abs(value);
    } else totals.expenses += expenseAmount(m);
  }
  return totals;
}
