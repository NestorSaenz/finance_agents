import { describe, expect, it } from "vitest";

import { formatPercent } from "@/lib/format";
import { summaryFigures, type SummaryFiguresInput } from "@/lib/summary";
import type {
  BudgetStatusList,
  GoalMonthlyHistory,
  GoalPlanStatusList,
  SpendingSummary,
  UserProfile,
} from "@/lib/types";

function summary(over: Partial<SpendingSummary> = {}): SpendingSummary {
  return {
    period: "este_mes",
    total_income: "10000000",
    total_expenses: "1000000",
    balance: "9000000",
    by_category: [],
    credit_expenses: "0",
    cash_expenses: "1000000",
    ...over,
  };
}

const profile = (over: Partial<UserProfile> = {}): UserProfile => ({
  display_name: null,
  monthly_income: "10000000",
  savings_goal_percentage: null,
  onboarding_completed: true,
  currency: "COP",
  timezone: null,
  ...over,
});

function plan(currency: string, amounts: string[] = ["500000"]): GoalPlanStatusList {
  const total = amounts.reduce((acc, a) => acc + Number(a), 0);
  return {
    statuses: amounts.map((a, i) => ({
      goal_id: `g${i}`,
      goal_name: `Meta ${i}`,
      currency,
      month: "2026-10",
      planned: a,
      effective_planned: a,
      contributed_gross: "0",
      withdrawn: "0",
      remaining: a,
      percentage: 0,
      is_met: false,
      goal_completed: false,
    })),
    total_planned: { [currency]: String(total) },
    total_effective_planned: { [currency]: String(total) },
    total_saved: { [currency]: "0" },
    total_withdrawn: { [currency]: "0" },
  };
}

function input(over: Partial<SummaryFiguresInput> = {}): SummaryFiguresInput {
  return {
    summary: summary(),
    budget: null,
    profile: profile(),
    goals: [],
    goalSaved: 0,
    goalWithdrawn: 0,
    cards: null,
    payments: null,
    planStatus: null,
    goalHistory: null,
    period: "este_mes",
    currency: "COP",
    ...over,
  };
}

describe("summaryFigures - income and spending", () => {
  it("Este mes with logged income: no base fallback; no goals means total = consumo", () => {
    const f = summaryFigures(input());
    expect(f.income).toBe(10000000);
    expect(f.usesBaseFallback).toBe(false);
    expect(f.expenses).toBe(1000000);
    expect(f.totalSpent).toBe(1000000);
    expect(f.balance).toBe(9000000);
    expect(f.afterSpending).toBe(9000000);
    expect(f.cashAvailable).toBe(9000000);
    expect(f.hasGoalFlow).toBe(false);
    expect(f.hasData).toBe(true);
  });

  it("falls back to the base income only in Este mes with no logged income", () => {
    const base = input({ summary: summary({ total_income: "0" }) });
    expect(summaryFigures(base)).toMatchObject({ income: 10000000, usesBaseFallback: true });
    expect(summaryFigures({ ...base, period: "mes_pasado" })).toMatchObject({
      income: 0,
      usesBaseFallback: false,
    });
    expect(summaryFigures({ ...base, period: "todo" }).income).toBe(0);
    expect(summaryFigures({ ...base, profile: null })).toMatchObject({
      income: 0,
      referenceIncome: 0,
      usesBaseFallback: false,
    });
  });

  it("an empty period has no data", () => {
    const f = summaryFigures(
      input({ summary: summary({ total_income: "0", total_expenses: "0", by_category: [] }) }),
    );
    expect(f.hasData).toBe(false);
  });

  it("a period with only goals still has data", () => {
    const f = summaryFigures(
      input({
        summary: summary({ total_income: "0", total_expenses: "0" }),
        goals: [
          { id: "g", name: "J", target_amount: "10", current_amount: "1", status: "active" },
          { id: "h", name: "K", target_amount: "10", current_amount: "1", status: "paused" },
        ],
      }),
    );
    expect(f.hasData).toBe(true);
    expect(f.activeGoals.map((g) => g.id)).toEqual(["g"]);
  });
});

describe("summaryFigures - goals with and without the cutoff", () => {
  it("aportes counted as gasto (goal_spending_from): total_spent includes them", () => {
    const f = summaryFigures(
      input({
        summary: summary({
          goal_saved: "500000",
          total_spent: "1500000",
          goal_withdrawn: "200000",
          goal_spending_from: "2026-10-01",
        }),
        goalSaved: 500000,
        goalWithdrawn: 200000,
        payments: { payments: [], total: "300000" },
      }),
    );
    expect(f.spentOnGoals).toBe(500000);
    expect(f.totalSpent).toBe(1500000);
    expect(f.balance).toBe(8500000);
    expect(f.goalsReturned).toBe(200000);
    // Flujo de caja never uses total_spent: cash + payments, goals gross.
    expect(f.afterSpending).toBe(8700000);
    expect(f.cashAvailable).toBe(8700000 - 500000 + 200000);
    expect(f.cashFlowNote).toBe(
      "Lo apartado a metas cuenta en tus gastos del mes y sale de tu caja (sigue siendo tuyo). Lo que retiraste de tus metas volvió a tu caja.",
    );
  });

  it("before the cutoff (no goal_saved) goals do not count as gasto and keep the old note", () => {
    const f = summaryFigures(input({ goalSaved: 500000 }));
    expect(f.spentOnGoals).toBe(0);
    expect(f.totalSpent).toBe(1000000);
    expect(f.cashAvailable).toBe(9000000 - 500000);
    expect(f.hasGoalFlow).toBe(true);
    expect(f.cashFlowNote).toBe("Apartar para metas reduce tu caja del mes, pero no es gasto.");
  });

  it("only withdrawals, and no goal movements, each have their own note", () => {
    expect(summaryFigures(input({ goalWithdrawn: 100 })).cashFlowNote).toBe(
      "Lo que retiraste de tus metas volvió a tu caja; no es un ingreso.",
    );
    expect(summaryFigures(input()).cashFlowNote).toBe(
      "Lo que te queda tras el efectivo y los pagos a tarjetas del mes.",
    );
  });

  it("falls back to total_expenses when total_spent is absent (older payloads)", () => {
    const f = summaryFigures(input({ summary: summary({ total_expenses: "777" }) }));
    expect(f.totalSpent).toBe(777);
    expect(f.spentOnGoals).toBe(0);
  });
});

describe("summaryFigures - pending plan", () => {
  it("is informational, Este mes only, and never enters a total", () => {
    const f = summaryFigures(input({ planStatus: plan("COP") }));
    expect(f.pending).toBe(500000);
    expect(f.hasPending).toBe(true);
    expect(f.afterPending).toBe(9000000 - 500000);
    expect(f.totalSpent).toBe(1000000);
    expect(f.cashAvailable).toBe(9000000);
    expect(f.hasCashFlow).toBe(true);
  });

  it("is zero in a past month, a chosen month or 'todo'", () => {
    for (const period of ["mes_pasado", "2026-09", "todo"]) {
      expect(summaryFigures(input({ planStatus: plan("COP"), period })).pending).toBe(0);
    }
  });

  it("is zero once the plan is met", () => {
    const met = plan("COP");
    const first = met.statuses[0];
    if (!first) throw new Error("fixture");
    first.remaining = "0";
    expect(summaryFigures(input({ planStatus: met })).hasPending).toBe(false);
  });

  it("a cash flow card is shown even without income when something is pending", () => {
    const f = summaryFigures(
      input({
        summary: summary({ total_income: "0", total_expenses: "0", cash_expenses: "0" }),
        profile: null,
        planStatus: plan("COP"),
      }),
    );
    expect(f.hasCashFlow).toBe(true);
    expect(f.afterPending).toBe(-500000);
  });
});

describe("summaryFigures - topes and plans against the base income", () => {
  const topes: BudgetStatusList = {
    statuses: [
      {
        budget: { id: "b1", name: "Mercado", category: "mercado", amount: "12700353" },
        spent: "0",
        remaining: "12700353",
        percentage: 0,
        alert_triggered: false,
        period_start: "2026-10-01",
        period_end: "2026-10-31",
      },
    ],
    total_budgeted: "12700353",
    total_spent: "0",
  };
  const history = (currency: string): GoalMonthlyHistory => ({
    lines: [
      {
        goal_id: "g0",
        goal_name: "Meta 0",
        currency,
        month: "2026-10",
        planned: "300000",
        saved: "0",
        withdrawn: "0",
        cumulative: "0",
      },
    ],
  });

  it("Astrid: MXN goals, COP profile, 3 plans, topes 12.700.353, income 14.350.000", () => {
    const f = summaryFigures(
      input({
        summary: summary({ total_income: "14350000" }),
        profile: profile({ monthly_income: "14350000" }),
        budget: topes,
        planStatus: plan("MXN", ["300000", "400000", "500000"]),
        goalHistory: history("MXN"),
      }),
    );
    expect(f.planCurrency).toBe("MXN");
    expect(f.plannedSaving).toBe(1200000);
    expect(f.planShare?.planned).toBe(1200000);
    expect(formatPercent(f.planShare?.plannedPct ?? 0)).toBe("8,4%");
    expect(f.planShare?.combined?.amount).toBe(13900353);
    expect(f.pending).toBe(1200000);
    expect(f.hasPlans).toBe(true);
    expect(f.hasTopes).toBe(true);
    expect(f.hasHistory).toBe(true);
    expect(f.topesShare?.categoryTotal).toBe(12700353);
  });

  it("COP goals under a COP profile behave the same", () => {
    const f = summaryFigures(
      input({
        profile: profile({ monthly_income: "14350000" }),
        planStatus: plan("COP", ["300000", "400000", "500000"]),
      }),
    );
    expect(f.planCurrency).toBe("COP");
    expect(f.plannedSaving).toBe(1200000);
  });

  it("COP and MXN goals: only the profile currency counts", () => {
    const mixed = plan("COP", ["300000"]);
    const mxn = plan("MXN", ["900000"]);
    const f = summaryFigures(
      input({
        planStatus: {
          ...mixed,
          statuses: [...mixed.statuses, ...mxn.statuses.map((s) => ({ ...s, goal_id: "gm" }))],
          total_effective_planned: { COP: "300000", MXN: "900000" },
        },
      }),
    );
    expect(f.planCurrency).toBe("COP");
    expect(f.plannedSaving).toBe(300000);
  });

  it("without base income there is no share of income, but plans still exist", () => {
    const f = summaryFigures(input({ profile: null, planStatus: plan("COP") }));
    expect(f.planShare).toBeNull();
    expect(f.topesShare).toBeNull();
    expect(f.hasPlans).toBe(true);
  });

  it("resolves the viewed month from the period with an injected clock", () => {
    const now = new Date(2026, 0, 31); // end of January: last month crosses the year
    expect(summaryFigures(input({ period: "2026-09", now })).viewedMonth).toBe("2026-09");
    expect(summaryFigures(input({ period: "este_mes", now })).viewedMonth).toBe("2026-01");
    expect(summaryFigures(input({ period: "mes_pasado", now })).viewedMonth).toBe("2025-12");
    expect(summaryFigures(input({ period: "todo", now })).viewedMonth).toBe("2026-01");
  });

  it("detects historical cards from missing statement periods", () => {
    const card = (statement_start: string | null) => ({ statement_start });
    const mk = (starts: Array<string | null>) =>
      ({ cards: starts.map(card) }) as unknown as SummaryFiguresInput["cards"];
    expect(summaryFigures(input({ cards: mk([null, null]) })).historicalCards).toBe(true);
    expect(summaryFigures(input({ cards: mk([null, "2026-10-01"]) })).historicalCards).toBe(false);
    expect(summaryFigures(input({ cards: mk([]) })).historicalCards).toBe(false);
  });
});

describe("summaryFigures - edge cases", () => {
  const NOW = new Date(2026, 10, 15);

  it("'todo': ends at the current month, nothing pending, no base fallback", () => {
    const f = summaryFigures(
      input({
        period: "todo",
        now: NOW,
        summary: summary({ total_income: "0" }),
        planStatus: plan("COP"),
      }),
    );
    expect(f.viewedMonth).toBe("2026-11");
    expect(f.pending).toBe(0);
    expect(f.hasPending).toBe(false);
    expect(f.usesBaseFallback).toBe(false);
    expect(f.income).toBe(0);
  });

  it("a profile without currency: the dashboard default (COP) is what arrives as input", () => {
    // The CurrencyContext defaults to COP, so SummaryContent always passes a code.
    const f = summaryFigures(input({ profile: profile({ currency: "" }), planStatus: plan("COP") }));
    expect(f.planCurrency).toBe("COP");
    expect(f.plannedSaving).toBe(500000);
  });

  it("activeGoals keeps active and completed, dropping paused and cancelled", () => {
    const goal = (id: string, status: "active" | "paused" | "completed" | "cancelled") => ({
      id,
      name: id,
      target_amount: "10",
      current_amount: "1",
      status,
    });
    const f = summaryFigures(
      input({
        goals: [
          goal("a", "active"),
          goal("p", "paused"),
          goal("c", "completed"),
          goal("x", "cancelled"),
        ],
      }),
    );
    expect(f.activeGoals.map((g) => g.id)).toEqual(["a", "c"]);
  });

  it("non-numeric amounts become NaN (same as before the refactor, not sanitised here)", () => {
    const f = summaryFigures(input({ summary: summary({ total_expenses: "abc" }) }));
    expect(Number.isNaN(f.expenses)).toBe(true);
    expect(Number.isNaN(f.totalSpent)).toBe(true);
  });
});
