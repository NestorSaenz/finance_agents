import { describe, expect, it } from "vitest";

import { MONTHS_ES } from "@/lib/format";
import { heroFigure, monthName } from "@/lib/heroFigure";
import { monthLabel } from "@/lib/goalPlans";
import { summaryFigures, type SummaryFiguresInput } from "@/lib/summary";
import type { SpendingSummary, UserProfile } from "@/lib/types";

const NOW = new Date(2026, 10, 15); // noviembre 2026
const money = (v: number) => `$${v}`;

function summary(over: Partial<SpendingSummary> = {}): SpendingSummary {
  return {
    period: "este_mes",
    total_income: "14350000",
    total_expenses: "8753132",
    balance: "0",
    by_category: [],
    credit_expenses: "0",
    cash_expenses: "3200000",
    ...over,
  };
}
const profile = (over: Partial<UserProfile> = {}): UserProfile => ({
  display_name: null,
  monthly_income: "14350000",
  savings_goal_percentage: null,
  onboarding_completed: true,
  currency: "COP",
  timezone: null,
  ...over,
});

function figures(over: Partial<SummaryFiguresInput> = {}) {
  return summaryFigures({
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
    now: NOW,
    ...over,
  });
}
const hero = (f: ReturnType<typeof figures>, period = "este_mes", surplus = 0) =>
  heroFigure(f, { period, accumulatedSurplus: surplus, money, now: NOW });

describe("monthName", () => {
  it("names the month, adding the year when it is not the current one", () => {
    expect(monthName("2026-11", NOW)).toBe("noviembre");
    expect(monthName("2025-03", NOW)).toBe("marzo 2025");
    expect(monthName("nope", NOW)).toBe("nope");
  });
});

describe("heroFigure - Este mes with income", () => {
  it("Astrid: base income 14.350.000 -> final cash and % consumed", () => {
    const f = figures({
      summary: summary({
        total_income: "0",
        total_expenses: "8753132",
        total_spent: "9253132",
        goal_saved: "500000",
        goal_spending_from: "2026-11-01",
        cash_expenses: "3200000",
      }),
      goalSaved: 500000,
      payments: { payments: [], total: "2100000" },
    });
    const h = hero(f);
    expect(h.kind).toBe("caja");
    expect(h.label).toBe("Tu mes · noviembre");
    // income (base fallback) - cash - card payments - saved
    expect(h.value).toBe(14350000 - 3200000 - 2100000 - 500000);
    expect(h.tone).toBe("positive");
    expect(h.bar?.pct).toBe(64.5); // 9.253.132 / 14.350.000
    expect(h.bar?.text).toBe("Consumido 64,5% de tu ingreso");
    expect(h.bar?.fill).toBe(64.5);
    expect(h.bar?.spent).toBe(9253132);
    expect(h.bar?.income).toBe(14350000);
    // The base-income note and the goals note stay visible.
    expect(h.notes).toEqual([
      "Incluye $500000 apartados a metas.",
      "Usando tu ingreso base $14350000. Registra o actualiza el de este mes para ajustarlo.",
    ]);
    expect(h.bar?.valueText).toContain("incluye lo apartado a metas");
    expect(h.subtitle).toContain("apartaste a metas");
  });

  it("with logged income there is no base-income note and no goals note without goals", () => {
    const h = hero(figures());
    expect(h.notes).toEqual([]);
    expect(h.bar?.valueText).toBe("Consumido 61% de tu ingreso");
    expect(h.subtitle).toBe("Caja final: lo que te queda después de lo que pagaste este mes.");
  });

  it("negative final cash has the negative tone", () => {
    const f = figures({
      summary: summary({ total_income: "1000000", total_expenses: "500000", cash_expenses: "1500000" }),
    });
    const h = hero(f);
    expect(h.value).toBe(-500000);
    expect(h.tone).toBe("negative");
  });

  it("over 100%: the bar clamps and the text says you spent more", () => {
    const f = figures({
      summary: summary({ total_income: "1000000", total_expenses: "1500000", cash_expenses: "100000" }),
    });
    const bar = hero(f).bar;
    expect(bar?.pct).toBe(150);
    expect(bar?.fill).toBe(100);
    expect(bar?.over).toBe(true);
    expect(bar?.text).toBe("Gastaste más que tu ingreso");
  });

  it("exactly 100% is not over", () => {
    const f = figures({
      summary: summary({ total_income: "1000000", total_expenses: "1000000", cash_expenses: "0" }),
    });
    const bar = hero(f).bar;
    expect(bar?.pct).toBe(100);
    expect(bar?.over).toBe(false);
    expect(bar?.text).toBe("Consumido 100% de tu ingreso");
  });

  it("with goal movements the subtitle mentions what was set aside", () => {
    expect(hero(figures({ goalSaved: 1 })).subtitle).toContain("apartaste a metas");
  });
});

describe("heroFigure - month picked / last month", () => {
  it("mes pasado WITH logged income leads with the final cash (no base fallback needed)", () => {
    const f = figures({ period: "mes_pasado" });
    const h = hero(f, "mes_pasado");
    expect(h.kind).toBe("caja");
    expect(h.label).toBe("Tu mes · octubre");
    expect(h.notes).toEqual([]);
  });

  it("a picked month names that month (and the year when it is another one)", () => {
    expect(hero(figures({ period: "2026-06" }), "2026-06").label).toBe("Tu mes · junio");
    expect(hero(figures({ period: "2025-12" }), "2025-12").label).toBe("Tu mes · diciembre 2025");
  });

  it("mes pasado WITHOUT income leads with the spending and asks for the income", () => {
    const f = figures({ period: "mes_pasado", summary: summary({ total_income: "0" }) });
    const h = hero(f, "mes_pasado");
    expect(h.kind).toBe("gastos");
    expect(h.value).toBe(8753132);
    expect(h.tone).toBe("negative");
    expect(h.bar).toBeNull();
    expect(h.subtitle).toContain("Registra tus ingresos para ver tu caja");
  });
});

describe("heroFigure - without income", () => {
  it("Este mes without income and without base income: spending, no bar", () => {
    const f = figures({ summary: summary({ total_income: "0" }), profile: null });
    const h = hero(f);
    expect(h.kind).toBe("gastos");
    expect(h.bar).toBeNull();
    expect(h.notes).toEqual([]);
  });

  it("includes the goals note when aportes count as gasto", () => {
    const f = figures({
      summary: summary({ total_income: "0", goal_saved: "500000", total_spent: "9253132" }),
      profile: null,
    });
    const h = hero(f);
    expect(h.value).toBe(9253132);
    expect(h.notes).toEqual(["Incluye $500000 apartados a metas."]);
  });

  it("zero spending without income is not negative", () => {
    const f = figures({
      summary: summary({ total_income: "0", total_expenses: "0", cash_expenses: "0", by_category: [{ category: "x", amount: "1", percentage: 1 }] }),
      profile: null,
    });
    expect(hero(f).tone).toBe("positive");
  });
});

describe("heroFigure - todo", () => {
  it("leads with the accumulated surplus and no consumption bar", () => {
    const h = hero(figures({ period: "todo" }), "todo", 5230000);
    expect(h.kind).toBe("excedente");
    expect(h.label).toBe("De toda tu historia");
    expect(h.value).toBe(5230000);
    expect(h.tone).toBe("positive");
    expect(h.bar).toBeNull();
  });

  it("a negative surplus has the negative tone", () => {
    expect(hero(figures({ period: "todo" }), "todo", -100).tone).toBe("negative");
  });

  it("'todo' ignores the base-income fallback", () => {
    const f = figures({ period: "todo", summary: summary({ total_income: "0" }) });
    expect(hero(f, "todo", 1).bar).toBeNull();
  });
});

describe("heroFigure - exact over-income decision and shared month names", () => {
  it("100,04% of the income is over it even though the % rounds to 100", () => {
    const f = figures({
      summary: summary({ total_income: "10000000", total_expenses: "10004000", cash_expenses: "0" }),
    });
    const bar = hero(f).bar;
    expect(bar?.pct).toBe(100);
    expect(bar?.over).toBe(true);
    expect(bar?.text).toBe("Gastaste más que tu ingreso");
    expect(bar?.fill).toBe(100);
  });

  it("spending exactly the income is not over", () => {
    const f = figures({
      summary: summary({ total_income: "10000000", total_expenses: "10000000", cash_expenses: "0" }),
    });
    expect(hero(f).bar?.over).toBe(false);
  });

  it("mes pasado with a base income but NO logged income takes the Gastos branch", () => {
    const f = figures({ period: "mes_pasado", summary: summary({ total_income: "0" }) });
    expect(f.referenceIncome).toBe(14350000);
    const h = hero(f, "mes_pasado");
    expect(h.kind).toBe("gastos");
    expect(h.bar).toBeNull();
  });

  it("monthName and monthLabel read the same MONTHS_ES list", () => {
    expect(MONTHS_ES).toHaveLength(12);
    MONTHS_ES.forEach((name, i) => {
      const key = `2026-${String(i + 1).padStart(2, "0")}`;
      expect(monthName(key, NOW)).toBe(name);
      expect(monthLabel(key)).toBe(`${name.charAt(0).toUpperCase()}${name.slice(1, 3)} 2026`);
    });
  });
});
