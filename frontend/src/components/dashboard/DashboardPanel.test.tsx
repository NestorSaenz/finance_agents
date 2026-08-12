import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardPanel } from "./DashboardPanel";

const {
  summaryMock,
  transactionsMock,
  budgetMock,
  profileMock,
  goalsMock,
  cardsMock,
  paymentsMock,
  contributionsMock,
  excedenteMock,
  recurringMock,
  ApiError,
} = vi.hoisted(() => {
  class ApiErrorMock extends Error {
    constructor(
      public readonly status: number,
      message: string,
    ) {
      super(message);
    }
  }
  return {
    summaryMock: vi.fn(),
    transactionsMock: vi.fn(),
    budgetMock: vi.fn(),
    profileMock: vi.fn(),
    goalsMock: vi.fn(),
    cardsMock: vi.fn(),
    paymentsMock: vi.fn(),
    contributionsMock: vi.fn(),
    excedenteMock: vi.fn(),
    recurringMock: vi.fn(),
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  api: {
    spendingSummary: (...args: unknown[]) => summaryMock(...args),
    transactions: (...args: unknown[]) => transactionsMock(...args),
    budgetStatus: (...args: unknown[]) => budgetMock(...args),
    profile: (...args: unknown[]) => profileMock(...args),
    goals: (...args: unknown[]) => goalsMock(...args),
    cardsStatus: (...args: unknown[]) => cardsMock(...args),
    cardPayments: (...args: unknown[]) => paymentsMock(...args),
    goalContributions: (...args: unknown[]) => contributionsMock(...args),
    excedente: (...args: unknown[]) => excedenteMock(...args),
    recurring: (...args: unknown[]) => recurringMock(...args),
  },
  ApiError,
}));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ token: "tok" }),
}));

const EMPTY_BUDGET = { statuses: [], total_budgeted: "0", total_spent: "0" };
const EMPTY_CARDS = {
  cards: [],
  total_limit: "0",
  total_balance: "0",
  total_available: "0",
};

function summary(overrides: Record<string, unknown> = {}) {
  return {
    period: "este_mes",
    total_income: "100000",
    total_expenses: "40000",
    balance: "60000",
    by_category: [{ category: "restaurantes", amount: "40000", percentage: 100 }],
    credit_expenses: "25000",
    cash_expenses: "15000",
    ...overrides,
  };
}

const PROFILE = {
  display_name: "Néstor",
  monthly_income: "10000000",
  savings_goal_percentage: "20",
  onboarding_completed: true,
};

beforeEach(() => {
  summaryMock.mockReset();
  transactionsMock.mockReset().mockResolvedValue({
    transactions: [],
    total: 0,
    page: 1,
    page_size: 0,
  });
  budgetMock.mockReset().mockResolvedValue(EMPTY_BUDGET);
  profileMock.mockReset().mockResolvedValue(PROFILE);
  goalsMock.mockReset().mockResolvedValue({ goals: [], total: 0, total_contributed: "0" });
  cardsMock.mockReset().mockResolvedValue(EMPTY_CARDS);
  paymentsMock.mockReset().mockResolvedValue({ payments: [], total: "0" });
  contributionsMock.mockReset().mockResolvedValue({ contributions: [], total: "0" });
  excedenteMock.mockReset().mockResolvedValue({ accumulated_surplus: "0" });
  recurringMock.mockReset().mockResolvedValue({ recurring: [], total: 0 });
});

describe("DashboardPanel", () => {
  it("loads totals and the payment split when opened", async () => {
    summaryMock.mockResolvedValue(summary());

    render(<DashboardPanel open onClose={() => {}} />);

    // "Ingresos" appears both as the stat card and inside the Flujo de caja block.
    expect((await screen.findAllByText("Ingresos")).length).toBeGreaterThan(0);
    expect(screen.getByText("Balance")).toBeInTheDocument();
    expect(screen.getByText("Flujo de caja")).toBeInTheDocument();
    // Spending-by-category section (lightweight bars, no chart library).
    expect(screen.getByText("Gastos por categoría")).toBeInTheDocument();
    // Credit vs cash split section rendered.
    expect(screen.getByText("Cómo pagas")).toBeInTheDocument();
    expect(screen.getByText("Crédito")).toBeInTheDocument();
    expect(summaryMock).toHaveBeenCalledWith("este_mes", "tok");
    expect(budgetMock).toHaveBeenCalledWith("tok");
  });

  it("shows the accumulated surplus, painting a negative value red", async () => {
    summaryMock.mockResolvedValue(summary());
    excedenteMock.mockResolvedValue({ accumulated_surplus: "-5000" });

    render(<DashboardPanel open onClose={() => {}} />);

    const label = await screen.findByText("Excedente acumulado");
    // The value sits in the same card; a negative surplus carries the "negative"
    // tone class, not the positive one (assert on the class, not the locale glyph).
    const value = label.parentElement?.querySelector("p.text-2xl");
    expect(value?.className).toContain("text-negative");
    expect(value?.className).not.toContain("text-positive");
    expect(excedenteMock).toHaveBeenCalledWith("este_mes", "tok");
  });

  it("shows budget progress when there are budgets", async () => {
    summaryMock.mockResolvedValue(summary());
    budgetMock.mockResolvedValue({
      statuses: [
        {
          budget: { id: "b1", name: "Comida", category: "alimentacion", amount: "5000" },
          spent: "3000",
          remaining: "2000",
          percentage: 60,
          alert_triggered: false,
        },
      ],
      total_budgeted: "5000",
      total_spent: "3000",
    });

    render(<DashboardPanel open onClose={() => {}} />);

    expect(await screen.findByText(/Cómo voy en cada categoría/i)).toBeInTheDocument();
    // Per-category budget row present.
    expect(screen.getByText("Alimentación")).toBeInTheDocument();
    // Income gauge uses the profile reference income.
    expect(screen.getByText("Gastos vs ingresos")).toBeInTheDocument();
  });

  it("shows savings goals with progress", async () => {
    summaryMock.mockResolvedValue(summary());
    goalsMock.mockResolvedValue({
      goals: [
        {
          id: "g1",
          name: "vacaciones playa",
          target_amount: "50000",
          current_amount: "20000",
          status: "active",
        },
      ],
      total: 1,
      total_contributed: "0",
    });

    render(<DashboardPanel open onClose={() => {}} />);

    expect(await screen.findByText("Metas de ahorro")).toBeInTheDocument();
    expect(screen.getByText("vacaciones playa")).toBeInTheDocument();
  });

  it("shows credit cards with debt and available credit", async () => {
    summaryMock.mockResolvedValue(summary());
    cardsMock.mockResolvedValue({
      cards: [
        {
          card: {
            id: "c1",
            name: "Visa BBVA",
            credit_limit: "5000000",
            cutoff_day: 15,
            payment_day: 5,
          },
          cycle_start: "2026-06-16",
          cycle_end: "2026-07-15",
          spent_cycle: "200000",
          balance: "500000",
          available: "4500000",
          utilization: 10,
          next_payment_date: "2026-08-05",
        },
      ],
      total_limit: "5000000",
      total_balance: "500000",
      total_available: "4500000",
    });

    render(<DashboardPanel open onClose={() => {}} />);

    expect(await screen.findByText("Tarjetas de crédito")).toBeInTheDocument();
    expect(screen.getByText("Visa BBVA")).toBeInTheDocument();
    expect(screen.getByText("Disponible")).toBeInTheDocument();
  });

  it("renders the Recurrentes card with grouped rows and the net", async () => {
    summaryMock.mockResolvedValue(summary());
    recurringMock.mockResolvedValue({
      recurring: [
        {
          id: "r1",
          description: "Sueldo",
          amount: "1000000",
          transaction_type: "income",
          category: null,
          payment_method: "efectivo",
          day_of_month: 1,
          next_run_date: "2026-09-01",
          active: true,
        },
        {
          id: "r2",
          description: "Arriendo",
          amount: "400000",
          transaction_type: "expense",
          category: "vivienda",
          payment_method: "efectivo",
          day_of_month: 5,
          next_run_date: "2026-09-05",
          active: true,
        },
        {
          id: "r3",
          description: "Netflix",
          amount: "50000",
          transaction_type: "expense",
          category: "suscripciones",
          payment_method: "efectivo",
          day_of_month: 10,
          next_run_date: "2026-09-10",
          active: false,
        },
      ],
      total: 3,
    });

    render(<DashboardPanel open onClose={() => {}} />);

    expect(await screen.findByText("Recurrentes")).toBeInTheDocument();
    expect(screen.getByText("Ingresos fijos")).toBeInTheDocument();
    expect(screen.getByText("Gastos fijos")).toBeInTheDocument();
    expect(screen.getByText("Sueldo")).toBeInTheDocument();
    expect(screen.getByText("Arriendo")).toBeInTheDocument();
    expect(screen.getByText("Netflix")).toBeInTheDocument();
    // The paused recurrente shows the "pausado" pill (text, not color-only).
    expect(screen.getByText("pausado")).toBeInTheDocument();
    // Net fijo = active income (1,000,000) − active expense (400,000) = 600,000;
    // the paused Netflix is excluded from the total.
    expect(screen.getByText("Neto fijo mensual")).toBeInTheDocument();
    expect(screen.getByText(/600,000/)).toBeInTheDocument();
    expect(recurringMock).toHaveBeenCalledWith("tok");
  });

  it("omits the Recurrentes card when there are none", async () => {
    summaryMock.mockResolvedValue(summary());

    render(<DashboardPanel open onClose={() => {}} />);
    await screen.findByText("Balance");

    expect(screen.queryByText("Recurrentes")).not.toBeInTheDocument();
  });

  it("requests a new period when a period tab is clicked", async () => {
    summaryMock.mockResolvedValue(
      summary({ total_income: "0", total_expenses: "0", balance: "0", by_category: [] }),
    );

    render(<DashboardPanel open onClose={() => {}} />);
    await screen.findByText(/Aún no hay movimientos/i);

    await userEvent.click(screen.getByText("Mes pasado"));

    await waitFor(() =>
      expect(summaryMock).toHaveBeenLastCalledWith("mes_pasado", "tok"),
    );
  });

  it("requests a specific month and skips budgets when a month is picked", async () => {
    summaryMock.mockResolvedValue(
      summary({ total_income: "0", total_expenses: "0", balance: "0", by_category: [] }),
    );

    render(<DashboardPanel open onClose={() => {}} />);
    await screen.findByText(/Aún no hay movimientos/i);
    budgetMock.mockClear();

    const select = screen.getByLabelText("Elegir un mes") as HTMLSelectElement;
    const monthValue = select.options[1].value; // first real month (skip the placeholder)
    await userEvent.selectOptions(select, monthValue);

    await waitFor(() =>
      expect(summaryMock).toHaveBeenLastCalledWith(monthValue, "tok"),
    );
    expect(paymentsMock).toHaveBeenLastCalledWith(monthValue, "tok");
    // Budgets are current-period only; a specific month must not fetch them.
    expect(budgetMock).not.toHaveBeenCalled();
  });

  it("lists individual movements when the Movimientos tab is opened", async () => {
    summaryMock.mockResolvedValue(summary());
    transactionsMock.mockResolvedValue({
      transactions: [
        {
          id: "tx-1",
          amount: "250000",
          description: "Televisor (cuota 1/4)",
          transaction_type: "expense",
          category: "tecnologia",
          payment_method: "credito",
          transaction_date: "2026-08-04",
          budget_date: "2026-08-04",
          created_at: "2026-08-04T00:00:00Z",
        },
        {
          id: "tx-2",
          amount: "465192",
          description: "Rappi SOAT",
          transaction_type: "expense",
          category: "transporte",
          payment_method: "credito",
          transaction_date: "2026-07-22",
          budget_date: "2026-09-05", // paid in September -> impact tag
          created_at: "2026-07-22T00:00:00Z",
        },
      ],
      total: 2,
      page: 1,
      page_size: 2,
    });

    render(<DashboardPanel open onClose={() => {}} />);
    await screen.findByText("Balance");

    await userEvent.click(screen.getByRole("button", { name: "Movimientos" }));

    // The description (with its installment marker) and category are shown.
    expect(await screen.findByText("Televisor (cuota 1/4)")).toBeInTheDocument();
    expect(screen.getByText(/Tecnología/)).toBeInTheDocument();
    // A credit charge paid a later month shows its impact-month tag.
    expect(screen.getByText(/impacta/)).toBeInTheDocument();
    expect(transactionsMock).toHaveBeenCalledWith("este_mes", "tok");
  });

  it("shows a goal contribution among the Movimientos", async () => {
    summaryMock.mockResolvedValue(summary());
    contributionsMock.mockResolvedValue({
      contributions: [
        {
          goal_name: "Viaje a Japón",
          amount: "150000",
          contribution_date: "2026-08-05",
        },
      ],
      total: "150000",
    });

    render(<DashboardPanel open onClose={() => {}} />);
    await screen.findByText("Balance");

    await userEvent.click(screen.getByRole("button", { name: "Movimientos" }));

    expect(await screen.findByText("Aporte a Viaje a Japón")).toBeInTheDocument();
    expect(contributionsMock).toHaveBeenCalledWith("este_mes", "tok");
  });

  it("refetches the summary when the refresh button is clicked", async () => {
    summaryMock.mockResolvedValue(summary());

    render(<DashboardPanel open onClose={() => {}} />);
    await screen.findByText("Balance");
    summaryMock.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Actualizar resumen" }));

    await waitFor(() => expect(summaryMock).toHaveBeenCalledTimes(1));
  });

  it("shows an error with a retry action when the request fails", async () => {
    summaryMock.mockRejectedValue(new ApiError(500, "boom"));

    render(<DashboardPanel open onClose={() => {}} />);

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.getByText("Reintentar")).toBeInTheDocument();
  });
});
