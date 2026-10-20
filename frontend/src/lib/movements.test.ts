import { describe, expect, it } from "vitest";

import { formatMoney } from "@/lib/format";
import {
  expenseAmount,
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
