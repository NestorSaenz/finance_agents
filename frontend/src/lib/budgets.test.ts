import { describe, expect, it } from "vitest";

import { budgetIncomeShare } from "@/lib/budgets";
import { formatPercent } from "@/lib/format";
import type { BudgetStatusItem } from "@/lib/types";

function status(
  id: string,
  amount: string,
  category: string | null = "otros",
  period_type?: "weekly" | "monthly" | "yearly",
): BudgetStatusItem {
  return {
    budget: { id, name: `Tope ${id}`, category, amount, period_type },
    spent: "0",
    remaining: amount,
    percentage: 0,
    alert_triggered: false,
    period_start: "2026-10-01",
    period_end: "2026-10-31",
  };
}

const ASTRID = [
  400000, 55000, 1334199, 100000, 1107000, 400000, 550000, 119900, 450000, 562754, 500000,
  1500000, 78500, 700000, 3493000, 1350000,
];

describe("budgetIncomeShare", () => {
  it("computes total and per-tope percentages", () => {
    const share = budgetIncomeShare(
      [status("a", "250000"), status("b", "750000", "mercado")],
      2000000,
    );
    expect(share?.categoryTotal).toBe(1000000);
    expect(share?.totalPct).toBe(50);
    expect(share?.pctById.get("a")).toBe(12.5);
    expect(share?.pctById.get("b")).toBe(37.5);
  });

  it("reproduces Astrid's numbers: 12.700.353 of 14.350.000 is 88,5%", () => {
    const statuses = ASTRID.map((a, i) => status(`s${i}`, String(a)));
    const share = budgetIncomeShare(statuses, 14350000);
    expect(share?.categoryTotal).toBe(12700353);
    expect(share?.totalPct).toBe(88.5);
    expect(formatPercent(share?.totalPct ?? 0)).toBe("88,5%");
    expect(formatPercent(share?.pctById.get("s14") ?? 0)).toBe("24,3%"); // transporte
    expect(formatPercent(share?.pctById.get("s11") ?? 0)).toBe("10,5%"); // mercado
  });

  it("returns null without usable income", () => {
    const list = [status("a", "100")];
    expect(budgetIncomeShare(list, undefined)).toBeNull();
    expect(budgetIncomeShare(list, null)).toBeNull();
    expect(budgetIncomeShare(list, 0)).toBeNull();
    expect(budgetIncomeShare(list, -5)).toBeNull();
    expect(budgetIncomeShare(list, Number.NaN)).toBeNull();
  });

  it("keeps an overall budget out of the total and reports it apart", () => {
    const share = budgetIncomeShare(
      [status("a", "300000"), status("o", "900000", null)],
      1000000,
    );
    expect(share?.categoryTotal).toBe(300000);
    expect(share?.totalPct).toBe(30);
    expect(share?.overall).toEqual({ amount: 900000, pct: 90 });
  });

  it("keeps the first overall budget when there are several", () => {
    const share = budgetIncomeShare(
      [status("o1", "900000", null), status("o2", "400000", null)],
      1000000,
    );
    expect(share?.overall).toEqual({ amount: 900000, pct: 90 });
  });

  it("excludes weekly and yearly budgets entirely", () => {
    const share = budgetIncomeShare(
      [
        status("m", "100000", "otros", "monthly"),
        status("w", "50000", "otros", "weekly"),
        status("y", "1200000", "otros", "yearly"),
      ],
      1000000,
    );
    expect(share?.categoryTotal).toBe(100000);
    expect(share?.pctById.has("w")).toBe(false);
    expect(share?.pctById.has("y")).toBe(false);
  });

  it("can exceed 100%", () => {
    expect(budgetIncomeShare([status("a", "1500")], 1000)?.totalPct).toBe(150);
  });
});

describe("formatPercent", () => {
  it("uses Spanish decimal comma, at most one decimal", () => {
    expect(formatPercent(88.5)).toBe("88,5%");
    expect(formatPercent(10)).toBe("10%");
  });
});
