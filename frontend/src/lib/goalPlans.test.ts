import { describe, expect, it } from "vitest";

import { formatPercent } from "@/lib/format";
import { planIncomeShare } from "@/lib/budgets";
import {
  goalHistory,
  historyTo,
  monthLabel,
  monthState,
  planFill,
  planTotals,
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

  it("orders one goal's rows and ends at the chosen month (future dropped)", () => {
    const lines = [
      line({ month: "2026-10" }),
      line({ month: "2026-08" }),
      line({ month: "2026-12" }), // future relative to the chosen month
      line({ goal_id: "g2", month: "2026-09" }),
    ];
    expect(goalHistory(lines, "g1", "2026-10").map((l) => l.month)).toEqual([
      "2026-08",
      "2026-10",
    ]);
  });

  it("classifies a month: sin plan, cumplido, faltan", () => {
    expect(monthState(line({ planned: null, saved: "100" }))).toMatchObject({ kind: "sin_plan" });
    expect(monthState(line({ saved: "500000" }))).toMatchObject({ kind: "cumplido", fill: 100 });
    expect(monthState(line({ saved: "320000" }))).toEqual({
      kind: "faltan",
      fill: 64,
      missing: 180000,
    });
  });
});

describe("monthState with zero / effective plans", () => {
  it("a plan of 0 means 'sin plan' (even when something was saved)", () => {
    expect(monthState(line({ planned: "0", saved: "0" }))).toMatchObject({ kind: "sin_plan" });
    expect(monthState(line({ planned: "0", saved: "100" }))).toMatchObject({ kind: "sin_plan" });
  });

  it("uses effective_planned for the fill and 'faltan', and falls back to planned", () => {
    expect(monthState(line({ planned: "500000", effective_planned: "400000", saved: "300000" }))).toEqual({
      kind: "faltan",
      fill: 75,
      missing: 100000,
    });
    // Capped plan already reached.
    expect(
      monthState(line({ planned: "500000", effective_planned: "250000", saved: "250000" })),
    ).toMatchObject({ kind: "cumplido" });
    for (const missing of [null, undefined]) {
      expect(
        monthState(line({ planned: "500000", effective_planned: missing, saved: "250000" })),
      ).toMatchObject({ kind: "faltan", missing: 250000 });
    }
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
