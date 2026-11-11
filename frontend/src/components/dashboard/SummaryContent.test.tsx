import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { formatMoney } from "@/lib/format";
import type {
  GoalPlanStatus,
  GoalPlanStatusList,
  SpendingSummary,
  UserProfile,
} from "@/lib/types";

import { SummaryContent } from "./SummaryContent";

// PaymentSplit must keep receiving consumo (total_expenses), not total_spent.
const paymentSplit = vi.hoisted(() => vi.fn());
vi.mock("./PaymentSplit", () => ({
  PaymentSplit: (props: { totalExpenses: number }) => {
    paymentSplit(props);
    return null;
  },
}));

const money = (value: number) => formatMoney(value);
/** formatMoney uses a no-break space; testing-library normalises it away. */
const text = (value: string) => (content: string) =>
  content.replace(/\s/g, " ") === value.replace(/\s/g, " ");
const digits = (el: Element | null | undefined) =>
  Number((el?.textContent ?? "").replace(/\D/g, ""));
const dd = (label: string) =>
  digits(screen.getByText(label, { selector: "dt" }).nextElementSibling);

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

const PROFILE: UserProfile = {
  display_name: null,
  monthly_income: "10000000",
  savings_goal_percentage: null,
  onboarding_completed: true,
  currency: "COP",
  timezone: null,
};

function planStatus(remaining: string, over: Partial<GoalPlanStatus> = {}): GoalPlanStatusList {
  return {
    statuses: [
      {
        goal_id: "g1",
        goal_name: "Viaje",
        currency: "COP",
        month: "2026-10",
        planned: "500000",
        effective_planned: "500000",
        contributed_gross: "0",
        withdrawn: "0",
        remaining,
        percentage: 0,
        is_met: remaining === "0",
        goal_completed: false,
        ...over,
      },
    ],
    total_planned: { COP: "500000" },
    total_effective_planned: { COP: "500000" },
    total_saved: { COP: "0" },
    total_withdrawn: { COP: "0" },
  };
}

function renderSummary(props: Partial<React.ComponentProps<typeof SummaryContent>> = {}) {
  return render(
    <SummaryContent
      summary={summary()}
      budget={null}
      budgetTransactions={[]}
      profile={PROFILE}
      goals={[]}
      goalSaved={0}
      goalWithdrawn={0}
      accumulatedSurplus={0}
      cards={null}
      payments={null}
      transactions={[]}
      recurring={[]}
      period="este_mes"
      {...props}
    />,
  );
}

const gastosCard = () => screen.getByText("Gastos").parentElement as HTMLElement;
const gastosValue = () => digits(gastosCard().querySelector("p:nth-of-type(2)"));

describe("SummaryContent - Gastos includes what was set aside to goals", () => {
  it("shows total_spent with a one-line breakdown when goal_saved > 0", () => {
    renderSummary({
      summary: summary({ goal_saved: "500000", total_spent: "1500000", goal_withdrawn: "0" }),
      goalSaved: 500000,
    });
    expect(gastosValue()).toBe(1500000);
    // Two short lines inside the card, not one long one.
    expect(within(gastosCard()).getByText(text(`consumo ${money(1000000)}`))).toBeInTheDocument();
    expect(
      within(gastosCard()).getByText(text(`+ apartado a metas ${money(500000)}`)),
    ).toBeInTheDocument();
  });

  it("without goal_saved the card is just consumo, with no breakdown (also for old payloads)", () => {
    renderSummary();
    expect(gastosValue()).toBe(1000000);
    expect(within(gastosCard()).queryByText(/consumo/)).toBeNull();
  });

  it("Balance and the gauge use total_spent", () => {
    renderSummary({
      summary: summary({ goal_saved: "500000", total_spent: "1500000" }),
      goalSaved: 500000,
    });
    const balance = screen.getByText("Balance").nextElementSibling;
    expect(digits(balance)).toBe(8500000); // 10.000.000 - 1.500.000
    expect(screen.getByText(/Incluye .* apartados a metas/)).toBeInTheDocument();
    expect(screen.getByText(/incluye lo apartado a metas/)).toBeInTheDocument();
  });

  it("notes goal withdrawals under Balance, using the endpoint value as is", () => {
    renderSummary({ summary: summary({ goal_withdrawn: "300000" }), goalWithdrawn: 999 });
    const note = screen.getByText(/Además volvieron .* de tus metas/);
    expect(note.textContent).toContain(money(300000));
  });

  it("July (aportes before the cutoff): Gastos = consumo, no breakdown, no withdrawal note", () => {
    // The endpoint reports goal_saved/goal_withdrawn = 0 for pre-cutoff months,
    // even though the contributions list still has movements.
    renderSummary({
      summary: summary({ goal_saved: "0", goal_withdrawn: "0", total_spent: "1000000" }),
      goalSaved: 500000,
      goalWithdrawn: 2000000,
    });
    expect(gastosValue()).toBe(1000000);
    expect(within(gastosCard()).queryByText(/consumo/)).toBeNull();
    expect(screen.queryByText(/Además volvieron/)).toBeNull();
    expect(screen.queryByText(/incluye lo apartado a metas/)).toBeNull();
    // The cash-flow lines still show the real movements, with the old wording.
    expect(dd("Apartado para metas")).toBe(500000);
    expect(
      screen.getByText(/Apartar para metas reduce tu caja del mes, pero no es gasto\./),
    ).toBeInTheDocument();
  });

  it("'Todo' crossing the cutoff: only the counted part is in Gastos", () => {
    renderSummary({
      period: "todo",
      summary: summary({ goal_saved: "200000", total_spent: "1200000", goal_withdrawn: "50000" }),
      goalSaved: 500000, // gross over the whole range, 300k of it before the cutoff
      goalWithdrawn: 400000,
    });
    expect(gastosValue()).toBe(1200000);
    expect(
      within(gastosCard()).getByText(text(`+ apartado a metas ${money(200000)}`)),
    ).toBeInTheDocument();
    expect(screen.getByText(/Además volvieron/).textContent).toContain(money(50000));
    // Flujo de caja keeps the gross movements of the whole range.
    expect(dd("Apartado para metas")).toBe(500000);
  });

  it("Flujo de caja values are IDENTICAL to before (cash + payments, saved once)", () => {
    renderSummary({
      summary: summary({ goal_saved: "500000", total_spent: "1500000" }),
      goalSaved: 500000,
      goalWithdrawn: 200000,
      payments: { payments: [], total: "300000" },
    });
    expect(dd("Efectivo")).toBe(1000000);
    expect(dd("Pagos a tarjetas")).toBe(300000);
    expect(dd("Te sobró")).toBe(8700000);
    expect(dd("Apartado para metas")).toBe(500000);
    // afterSpending - saved + withdrawn, never using total_spent.
    expect(dd("Caja final del mes")).toBe(8700000 - 500000 + 200000);
  });

  it("'Disponible del mes' is unchanged without goal movements", () => {
    renderSummary();
    expect(dd("Disponible del mes")).toBe(9000000);
  });

  it("PaymentSplit keeps receiving consumo", () => {
    paymentSplit.mockClear();
    renderSummary({ summary: summary({ goal_saved: "500000", total_spent: "1500000" }) });
    expect(paymentSplit).toHaveBeenCalledWith(expect.objectContaining({ totalExpenses: 1000000 }));
  });

  it("flow note: new wording when aportes count as gasto, old one before the cutoff", () => {
    const { unmount } = renderSummary({
      summary: summary({ goal_saved: "500000", total_spent: "1500000" }),
      goalSaved: 500000,
    });
    expect(
      screen.getByText(
        "Lo apartado a metas cuenta en tus gastos del mes y sale de tu caja (sigue siendo tuyo).",
      ),
    ).toBeInTheDocument();
    unmount();
    renderSummary({ goalSaved: 500000 }); // goal_saved absent -> before the cutoff
    expect(
      screen.getByText("Apartar para metas reduce tu caja del mes, pero no es gasto."),
    ).toBeInTheDocument();
  });
});

describe("SummaryContent - 'Por aportar' (pending plan)", () => {
  it("Astrid: plan 500k not contributed -> informational line, Z and G, no totals touched", () => {
    renderSummary({ planStatus: planStatus("500000") });
    const line = screen.getByText(/Por aportar a tus metas este mes/);
    expect(digits(line)).toBe(500000);
    // Z = caja final (9.000.000) - 500.000 ; G = gastos (1.000.000) + 500.000.
    const ifPaid = screen.getByText(/Si lo aportas, tu caja final quedaría en/);
    expect(ifPaid.parentElement?.textContent).toContain(money(8500000));
    expect(ifPaid.parentElement?.textContent).toContain(money(1500000));
    expect(
      screen.getByText("Es un plan: no cuenta como gasto hasta que registres el aporte."),
    ).toBeInTheDocument();
    // Totals unchanged.
    expect(dd("Disponible del mes")).toBe(9000000);
    expect(gastosValue()).toBe(1000000);
    expect(
      within(gastosCard()).getByText(text(`sin contar ${money(500000)} por aportar`)),
    ).toBeInTheDocument();
  });

  it("is shown even with no goal movements and never in red; amber when it would not fit", () => {
    renderSummary({
      summary: summary({ total_income: "300000", total_expenses: "0", cash_expenses: "0" }),
      profile: { ...PROFILE, monthly_income: "300000" },
      planStatus: planStatus("500000"),
    });
    const ifPaid = screen.getByText(/Si lo aportas, te faltarían/);
    expect(ifPaid.querySelector("span")?.className).toContain("text-amber-700");
    expect(ifPaid.parentElement?.innerHTML).not.toMatch(/negative/);
  });

  it("disappears once the plan is met, and outside 'Este mes'", () => {
    const { unmount } = renderSummary({ planStatus: planStatus("0") });
    expect(screen.queryByText(/Por aportar a tus metas/)).toBeNull();
    unmount();
    const { unmount: unmount2 } = renderSummary({
      planStatus: planStatus("500000"),
      period: "mes_pasado",
    });
    expect(screen.queryByText(/Por aportar a tus metas/)).toBeNull();
    unmount2();
    renderSummary({ planStatus: planStatus("500000"), period: "2026-09" });
    expect(screen.queryByText(/Por aportar a tus metas/)).toBeNull();
    expect(within(gastosCard()).queryByText(/por aportar/)).toBeNull();
  });
});

describe("SummaryContent - goals labelled with another currency (Astrid: MXN goals, COP profile)", () => {
  const mxnPlan = (currencies: [string, string, string] = ["MXN", "MXN", "MXN"]): GoalPlanStatusList => {
    const amounts = ["300000", "400000", "500000"];
    return {
      statuses: amounts.map((a, i) => ({
        goal_id: `g${i}`,
        goal_name: `Meta ${i}`,
        currency: currencies[i] ?? "MXN",
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
      total_planned: { MXN: "1200000" },
      total_effective_planned: { MXN: "1200000" },
      total_saved: { MXN: "0" },
      total_withdrawn: { MXN: "0" },
    };
  };

  const topes = {
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

  const astrid = {
    profile: { ...PROFILE, monthly_income: "14350000" },
    summary: summary({ total_income: "14350000" }),
  };

  it("shows plan % of income, Topes + metas, 'Por aportar' and the history", () => {
    renderSummary({
      ...astrid,
      budget: topes,
      planStatus: mxnPlan(),
      goalHistory: {
        lines: [
          {
            goal_id: "g0",
            goal_name: "Meta 0",
            currency: "MXN",
            month: "2026-10",
            planned: "300000",
            saved: "0",
            withdrawn: "0",
            cumulative: "0",
          },
        ],
      },
      onSelectMonth: () => {},
    });
    const planLine = screen.getByText(/Ahorro planificado del mes.+ingreso/);
    expect(planLine.textContent).toContain(money(1200000));
    expect(planLine.textContent).toContain("8,4%");
    const combined = screen.getByText(/Topes \+ metas/);
    expect(combined.textContent).toContain(money(12700353 + 1200000));
    expect(screen.getByText(/Por aportar a tus metas este mes/).textContent).toContain(
      money(1200000),
    );
    expect(screen.getByRole("button", { name: /Historial de planes/ })).toBeInTheDocument();
    // The plan block shows the amounts in the profile currency, not MXN.
    expect(screen.getByText(text(`${money(0)} / ${money(300000)}`))).toBeInTheDocument();
  });

  it("with a COP profile and COP goals nothing changes", () => {
    renderSummary({
      ...astrid,
      budget: topes,
      planStatus: {
        ...mxnPlan(["COP", "COP", "COP"]),
        total_effective_planned: { COP: "1200000" },
        total_planned: { COP: "1200000" },
        total_saved: { COP: "0" },
        total_withdrawn: { COP: "0" },
      },
    });
    expect(screen.getByText(/Ahorro planificado del mes.+ingreso/).textContent).toContain("8,4%");
  });

  it("with COP and MXN goals only COP counts (no mixing)", () => {
    renderSummary({
      ...astrid,
      planStatus: {
        ...mxnPlan(["COP", "MXN", "MXN"]),
        total_effective_planned: { COP: "300000", MXN: "900000" },
        total_planned: { COP: "300000", MXN: "900000" },
        total_saved: { COP: "0", MXN: "0" },
        total_withdrawn: { COP: "0", MXN: "0" },
      },
    });
    expect(screen.getByText(/Ahorro planificado del mes.+ingreso/).textContent).toContain(
      money(300000),
    );
    expect(screen.getByText(/Por aportar a tus metas este mes/).textContent).toContain(
      money(300000),
    );
  });

  it("with two foreign currencies and none the profile's, no plan line is invented", () => {
    renderSummary({
      ...astrid,
      planStatus: {
        ...mxnPlan(["MXN", "USD", "USD"]),
        total_effective_planned: { MXN: "300000", USD: "900000" },
        total_planned: { MXN: "300000", USD: "900000" },
        total_saved: { MXN: "0", USD: "0" },
        total_withdrawn: { MXN: "0", USD: "0" },
      },
    });
    expect(screen.queryByText(/Ahorro planificado del mes.+ingreso/)).toBeNull();
    expect(screen.queryByText(/Por aportar a tus metas/)).toBeNull();
  });
});
