import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardPanel } from "./DashboardPanel";

const {
  summaryMock,
  budgetMock,
  profileMock,
  goalsMock,
  cardsMock,
  paymentsMock,
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
    budgetMock: vi.fn(),
    profileMock: vi.fn(),
    goalsMock: vi.fn(),
    cardsMock: vi.fn(),
    paymentsMock: vi.fn(),
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  api: {
    spendingSummary: (...args: unknown[]) => summaryMock(...args),
    budgetStatus: (...args: unknown[]) => budgetMock(...args),
    profile: (...args: unknown[]) => profileMock(...args),
    goals: (...args: unknown[]) => goalsMock(...args),
    cardsStatus: (...args: unknown[]) => cardsMock(...args),
    cardPayments: (...args: unknown[]) => paymentsMock(...args),
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
  budgetMock.mockReset().mockResolvedValue(EMPTY_BUDGET);
  profileMock.mockReset().mockResolvedValue(PROFILE);
  goalsMock.mockReset().mockResolvedValue({ goals: [], total: 0 });
  cardsMock.mockReset().mockResolvedValue(EMPTY_CARDS);
  paymentsMock.mockReset().mockResolvedValue({ payments: [], total: "0" });
});

describe("DashboardPanel", () => {
  it("loads totals and the payment split when opened", async () => {
    summaryMock.mockResolvedValue(summary());

    render(<DashboardPanel open onClose={() => {}} />);

    // Profile has a reference income, so registered income is "adicionales".
    expect(await screen.findByText("Ingresos adicionales")).toBeInTheDocument();
    expect(screen.getByText("Ingreso base (referencia)")).toBeInTheDocument();
    expect(screen.getByText("Balance")).toBeInTheDocument();
    // Spending-by-category section (lightweight bars, no chart library).
    expect(screen.getByText("Gastos por categoría")).toBeInTheDocument();
    // Credit vs cash split section rendered.
    expect(screen.getByText("Cómo pagas")).toBeInTheDocument();
    expect(screen.getByText("Crédito")).toBeInTheDocument();
    expect(summaryMock).toHaveBeenCalledWith("este_mes", "tok");
    expect(budgetMock).toHaveBeenCalledWith("tok");
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

  it("shows an error with a retry action when the request fails", async () => {
    summaryMock.mockRejectedValue(new ApiError(500, "boom"));

    render(<DashboardPanel open onClose={() => {}} />);

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.getByText("Reintentar")).toBeInTheDocument();
  });
});
