import { describe, expect, it } from "vitest";

import { formatMoney } from "@/lib/format";
import {
  expenseAmount,
  goalFlows,
  isCashMovement,
  isCashTx,
  movementTotals,
  type Movement,
} from "@/lib/movements";
import type { Transaction } from "@/lib/types";

function tx(over: Partial<Transaction> = {}): Transaction {
  return {
    id: "t1",
    amount: "100",
    description: "x",
    transaction_type: "expense",
    category: "salud",
    payment_method: "efectivo",
    card_id: null,
    transaction_date: "2026-06-10",
    budget_date: "2026-06-10",
    created_at: "2026-06-10T00:00:00Z",
    ...over,
  };
}
const txm = (over: Partial<Transaction> = {}): Movement => ({
  kind: "tx",
  date: "2026-06-10",
  tx: tx(over),
});
const contrib = (amount: string): Movement => ({
  kind: "contribution",
  date: "2026-06-10",
  id: "c",
  goalName: "Meta",
  amount,
});
const pay = (amount: string): Movement => ({
  kind: "payment",
  date: "2026-06-10",
  id: "p",
  cardName: "Nu",
  amount,
});

describe("isCashTx", () => {
  it("treats an untagged, card-less tx as cash", () => {
    expect(isCashTx(tx({ payment_method: null, card_id: null }))).toBe(true);
  });
  it("does not treat credito without card_id as cash", () => {
    expect(isCashTx(tx({ payment_method: "credito", card_id: null }))).toBe(false);
  });
  it("card-linked: null method is not cash, explicit efectivo is", () => {
    expect(isCashTx(tx({ payment_method: null, card_id: "c1" }))).toBe(false);
    expect(isCashTx(tx({ payment_method: "efectivo", card_id: "c1" }))).toBe(true);
  });
  it("lists payments and goal rows under cash", () => {
    expect(isCashMovement(pay("1"))).toBe(true);
    expect(isCashMovement(contrib("1"))).toBe(true);
  });
});

describe("expenseAmount / movementTotals", () => {
  it("never counts income, payments or goal rows as expense", () => {
    expect(expenseAmount(txm({ transaction_type: "income", amount: "999" }))).toBe(0);
    expect(expenseAmount(pay("500"))).toBe(0);
    expect(expenseAmount(contrib("500"))).toBe(0);
  });

  it("splits goals into gross saved / withdrawn and keeps them out of expenses", () => {
    const t = movementTotals([
      txm({ amount: "100" }),
      pay("300"),
      contrib("500"),
      contrib("-2000"),
    ]);
    expect(t).toEqual({ expenses: 100, paid: 300, saved: 500, withdrawn: 2000 });
  });

  it("sums decimal strings; the money formatter hides float drift", () => {
    const t = movementTotals([txm({ amount: "0.10" }), txm({ id: "2", amount: "0.20" })]);
    expect(t.expenses).not.toBe(0.3); // 0.30000000000000004
    // Same pure formatter useMoney() binds to the user's currency.
    expect(formatMoney(t.expenses, "COP")).toBe(formatMoney(0.3, "COP"));
    expect(formatMoney(t.expenses, "USD")).toBe(formatMoney(0.3, "USD"));
  });
});

describe("goalFlows", () => {
  const rows = (...amounts: string[]) => amounts.map((amount) => ({ amount }));

  it("keeps saved and withdrawn gross (Astrid's October)", () => {
    expect(goalFlows(rows("200000", "300000", "-2000000", "-1100000"))).toEqual({
      saved: 500000,
      withdrawn: 3100000,
    });
  });
  it("handles only saves, only withdrawals and empty", () => {
    expect(goalFlows(rows("100", "50"))).toEqual({ saved: 150, withdrawn: 0 });
    expect(goalFlows(rows("-100", "-50"))).toEqual({ saved: 0, withdrawn: 150 });
    expect(goalFlows([])).toEqual({ saved: 0, withdrawn: 0 });
  });
  it("does not net a month that nets to zero", () => {
    expect(goalFlows(rows("100000", "-100000"))).toEqual({ saved: 100000, withdrawn: 100000 });
  });
  it("skips non-finite amounts", () => {
    expect(goalFlows(rows("abc", "100", "NaN", "-50"))).toEqual({ saved: 100, withdrawn: 50 });
  });
  it("movementTotals reuses it", () => {
    expect(movementTotals([contrib("500"), contrib("-200")])).toMatchObject({
      saved: 500,
      withdrawn: 200,
    });
  });
});
