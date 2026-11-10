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

/** What a row adds to the Resumen "Gastos" (total_spent): an expense's amount, or
 *  a positive goal aporte dated on/after `goalSpendingFrom` (the cutoff; without
 *  one aportes do not count). Payments, withdrawals and income add 0. */
export function spentAmount(m: Movement, goalSpendingFrom?: string | null): number {
  if (m.kind === "contribution") {
    const value = Number(m.amount);
    return goalSpendingFrom && m.date >= goalSpendingFrom && value > 0 ? value : 0;
  }
  return expenseAmount(m);
}

export interface MovementTotals {
  /** Gross aportes counted as gasto (dated on/after the cutoff). */
  savedSpent: number;
  /** Σ expense transactions (any payment method). */
  expenses: number;
  /** Σ card payments. */
  paid: number;
  /** Gross goal aportes (positive contributions). */
  saved: number;
  /** Gross goal retiros (|negative contributions|). */
  withdrawn: number;
}

/** Gross goal flows: saved (aportes, positive amounts) and withdrawn (retiros,
 *  |negative amounts|). Never a net — both are positive numbers. */
export interface GoalFlows {
  saved: number;
  withdrawn: number;
}

export function goalFlows(contributions: ReadonlyArray<{ amount: string }>): GoalFlows {
  const flows: GoalFlows = { saved: 0, withdrawn: 0 };
  for (const c of contributions) {
    const value = Number(c.amount);
    if (!Number.isFinite(value)) continue;
    if (value > 0) flows.saved += value;
    else flows.withdrawn += Math.abs(value);
  }
  return flows;
}

/** Totals over a list of movements. Goal movements never count as expense. */
export function movementTotals(
  list: Movement[],
  goalSpendingFrom?: string | null,
): MovementTotals {
  let expenses = 0;
  let savedSpent = 0;
  let paid = 0;
  const goalRows: { amount: string }[] = [];
  for (const m of list) {
    if (m.kind === "payment") paid += Number(m.amount);
    else if (m.kind === "contribution") {
      goalRows.push(m);
      savedSpent += spentAmount(m, goalSpendingFrom);
    } else expenses += expenseAmount(m);
  }
  return { expenses, paid, savedSpent, ...goalFlows(goalRows) };
}
