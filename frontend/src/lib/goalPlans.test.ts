import { describe, expect, it } from "vitest";

import { formatPercent } from "@/lib/format";
import { planIncomeShare } from "@/lib/budgets";
import {
  historyTo,
  monthLabel,
  monthSummaries,
  pendingSavingFor,
  planFill,
  planCurrencies,
  planTotals,
  resolveCurrency,
  plannedSavingFor,
  selectedMonth,
  visiblePlans,
} from "@/lib/goalPlans";
import type { GoalMonthLine, GoalPlanStatus, GoalPlanStatusList } from "@/lib/types";

function status(over: Partial<GoalPlanStatus> = {}): GoalPlanStatus {
  return {
    goal_id: "g1",
    goal_name: "Viaje",
    currency: "COP",
    month: "2026-10",
    planned: "500000",
    effective_planned: "500000",
    contributed_gross: "0",
    withdrawn: "0",
    remaining: "500000",
    percentage: 0,
    is_met: false,
    goal_completed: false,
    ...over,
  };
}

function list(over: Partial<GoalPlanStatusList> = {}): GoalPlanStatusList {
  return {
    statuses: [],
    total_planned: {},
    total_effective_planned: {},
    total_saved: {},
    total_withdrawn: {},
    ...over,
  };
}

function line(over: Partial<GoalMonthLine> = {}): GoalMonthLine {
  return {
    goal_id: "g1",
    goal_name: "Viaje",
    currency: "COP",
    month: "2026-10",
    planned: "500000",
    saved: "0",
    withdrawn: "0",
    cumulative: "0",
    ...over,
  };
}

describe("planTotals / plannedSavingFor", () => {
  it("has no totals without plans", () => {
    expect(planTotals(list())).toEqual([]);
    expect(plannedSavingFor(list(), "COP")).toBe(0);
    expect(plannedSavingFor(null, "COP")).toBe(0);
  });

  it("keeps currencies apart and sorted", () => {
    const l = list({
      total_effective_planned: { USD: "100", COP: "500000" },
      total_saved: { COP: "200000" },
    });
    expect(planTotals(l)).toEqual([
      { currency: "COP", planned: 500000, saved: 200000 },
      { currency: "USD", planned: 100, saved: 0 },
    ]);
    expect(plannedSavingFor(l, "COP")).toBe(500000);
    expect(plannedSavingFor(l, "USD")).toBe(100);
    expect(plannedSavingFor(l, "MXN")).toBe(0);
  });
});

describe("planFill / visiblePlans", () => {
  it("clamps the fill to 0-100", () => {
    expect(planFill(status({ percentage: 64 }))).toBe(64);
    expect(planFill(status({ percentage: 250 }))).toBe(100);
    expect(planFill(status({ percentage: -3 }))).toBe(0);
    expect(planFill(status({ percentage: Number.NaN }))).toBe(0);
  });

  it("hides rows without any plan", () => {
    const l = list({
      statuses: [status(), status({ goal_id: "g2", planned: "0", effective_planned: "0" })],
    });
    expect(visiblePlans(l).map((s) => s.goal_id)).toEqual(["g1"]);
    expect(visiblePlans(null)).toEqual([]);
  });
});

describe("month helpers", () => {
  it("labels months in Spanish", () => {
    expect(monthLabel("2026-11")).toBe("Nov 2026");
    expect(monthLabel("2026-01")).toBe("Ene 2026");
    expect(monthLabel("nope")).toBe("nope");
  });

  it("resolves the selected month and the 'to' parameter", () => {
    const now = new Date(2026, 0, 15); // January: last month crosses the year
    expect(selectedMonth("este_mes", now)).toBe("2026-01");
    expect(selectedMonth("todo", now)).toBe("2026-01");
    expect(selectedMonth("mes_pasado", now)).toBe("2025-12");
    expect(selectedMonth("2026-06", now)).toBe("2026-06");
    expect(historyTo("este_mes", now)).toBeUndefined();
    expect(historyTo("todo", now)).toBeUndefined();
    expect(historyTo("mes_pasado", now)).toBe("2025-12");
    expect(historyTo("2026-06", now)).toBe("2026-06");
  });
});

describe("pendingSavingFor", () => {
  it("sums what is still missing in the profile currency only", () => {
    const l = list({
      statuses: [
        status({ remaining: "500000" }),
        status({ goal_id: "g2", remaining: "0", is_met: true }),
        status({ goal_id: "g3", remaining: "100", currency: "USD" }),
      ],
    });
    expect(pendingSavingFor(l, "COP")).toBe(500000);
    expect(pendingSavingFor(l, "USD")).toBe(100);
    expect(pendingSavingFor(null, "COP")).toBe(0);
  });
});

describe("monthSummaries", () => {
  const lines = [
    line({ month: "2026-09", planned: "500000", saved: "500000" }),
    line({ goal_id: "g2", month: "2026-09", planned: "300000", saved: "100000" }),
    line({ month: "2026-10", planned: "500000", effective_planned: "400000", saved: "400000" }),
    line({ month: "2026-08", planned: null, saved: "50" }),
    line({ month: "2026-07", planned: "0", saved: "0" }),
    line({ goal_id: "g3", currency: "USD", month: "2026-10", planned: "100", saved: "10" }),
    line({ month: "2026-12", planned: "1", saved: "1" }),
  ];

  it("summarises per month, oldest first, only the given currency", () => {
    expect(monthSummaries(lines, "COP", "2026-10")).toEqual([
      { month: "2026-09", planned: 800000, saved: 600000, met: 1, total: 2 },
      { month: "2026-10", planned: 400000, saved: 400000, met: 1, total: 1 },
    ]);
  });

  it("leaves out months without plan (null or 0) and keeps currencies apart", () => {
    const months = monthSummaries(lines, "COP").map((m) => m.month);
    expect(months).not.toContain("2026-08");
    expect(months).not.toContain("2026-07");
    expect(monthSummaries(lines, "USD")).toEqual([
      { month: "2026-10", planned: 100, saved: 10, met: 0, total: 1 },
    ]);
  });
});

describe("planIncomeShare", () => {
  it("is null without income or plan", () => {
    expect(planIncomeShare(null, 100, 0)).toBeNull();
    expect(planIncomeShare(0, 100, 0)).toBeNull();
    expect(planIncomeShare(1000, 0, 500)).toBeNull();
  });

  it("computes the plan percentage with one decimal (Spanish format)", () => {
    const share = planIncomeShare(14350000, 1500000, 0);
    expect(share?.plannedPct).toBe(10.5);
    expect(formatPercent(share?.plannedPct ?? 0)).toBe("10,5%");
    expect(share?.combined).toBeNull();
  });

  it("adds topes + plan as a combined line only when there are topes", () => {
    const share = planIncomeShare(14350000, 1500000, 12700353);
    expect(share?.combined?.amount).toBe(14200353);
    expect(share?.combined?.pct).toBe(99);
    expect(share?.exceedsIncome).toBe(false);
  });

  it("flags only the combined overflow (topes alone already have their note)", () => {
    expect(planIncomeShare(1000, 300, 800)?.exceedsIncome).toBe(true);
    expect(planIncomeShare(1000, 300, 1200)?.exceedsIncome).toBe(false);
    expect(planIncomeShare(1000, 1200, 0)?.exceedsIncome).toBe(true);
  });
});

describe("resolveCurrency", () => {
  it("prefers the profile currency when any data uses it", () => {
    expect(resolveCurrency(["COP", "MXN"], "COP")).toBe("COP");
    expect(resolveCurrency(["COP"], "COP")).toBe("COP");
  });

  it("adopts the single other currency (goals mislabelled MXN for a COP user)", () => {
    expect(resolveCurrency(["MXN", "MXN", "MXN"], "COP")).toBe("MXN");
  });

  it("keeps the profile currency when several foreign currencies exist (no mixing)", () => {
    expect(resolveCurrency(["MXN", "USD"], "COP")).toBe("COP");
  });

  it("returns the profile currency when there is no data", () => {
    expect(resolveCurrency([], "COP")).toBe("COP");
  });

  it("planCurrencies gathers plan-status and history currencies", () => {
    const l = list({
      statuses: [status({ currency: "MXN" })],
      total_effective_planned: { MXN: "1" },
    });
    expect(planCurrencies(l, { lines: [line({ currency: "USD" })] }).sort()).toEqual([
      "MXN",
      "MXN",
      "USD",
    ]);
    expect(planCurrencies(null, null)).toEqual([]);
  });
});
