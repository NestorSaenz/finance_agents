import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardPanel } from "./DashboardPanel";

const mocks = vi.hoisted(() => ({
  summary: vi.fn(),
  transactions: vi.fn(),
  budget: vi.fn(),
  profile: vi.fn(),
  goals: vi.fn(),
  cards: vi.fn(),
  payments: vi.fn(),
  contributions: vi.fn(),
  excedente: vi.fn(),
  recurring: vi.fn(),
  plan: vi.fn(),
  monthly: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    spendingSummary: (...a: unknown[]) => mocks.summary(...a),
    transactions: (...a: unknown[]) => mocks.transactions(...a),
    budgetStatus: (...a: unknown[]) => mocks.budget(...a),
    profile: (...a: unknown[]) => mocks.profile(...a),
    goals: (...a: unknown[]) => mocks.goals(...a),
    cardsStatus: (...a: unknown[]) => mocks.cards(...a),
    cardPayments: (...a: unknown[]) => mocks.payments(...a),
    goalContributions: (...a: unknown[]) => mocks.contributions(...a),
    excedente: (...a: unknown[]) => mocks.excedente(...a),
    recurring: (...a: unknown[]) => mocks.recurring(...a),
    goalPlanStatus: (...a: unknown[]) => mocks.plan(...a),
    goalMonthly: (...a: unknown[]) => mocks.monthly(...a),
  },
  ApiError: class ApiError extends Error {},
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ token: "tok" }) }));

beforeEach(() => {
  window.localStorage.clear();
  mocks.summary.mockReset().mockResolvedValue({
    period: "este_mes",
    total_income: "100000",
    total_expenses: "40000",
    balance: "60000",
    by_category: [{ category: "restaurantes", amount: "40000", percentage: 100 }],
    credit_expenses: "25000",
    cash_expenses: "15000",
  });
  mocks.transactions.mockReset().mockResolvedValue({ transactions: [], total: 0, page: 1, page_size: 0 });
  mocks.budget.mockReset().mockResolvedValue({ statuses: [], total_budgeted: "0", total_spent: "0" });
  mocks.profile.mockReset().mockResolvedValue({
    display_name: "N",
    monthly_income: "10000000",
    savings_goal_percentage: "20",
    onboarding_completed: true,
  });
  mocks.goals.mockReset().mockResolvedValue({ goals: [], total: 0, total_contributed: "0" });
  mocks.cards.mockReset().mockResolvedValue({ cards: [], total_limit: "0", total_balance: "0", total_available: "0" });
  mocks.payments.mockReset().mockResolvedValue({ payments: [], total: "0" });
  mocks.contributions.mockReset().mockResolvedValue({ contributions: [], total: "0" });
  mocks.excedente.mockReset().mockResolvedValue({ accumulated_surplus: "500" });
  mocks.recurring.mockReset().mockResolvedValue({ recurring: [], total: 0 });
  mocks.plan.mockReset().mockResolvedValue({
    statuses: [],
    total_planned: {},
    total_effective_planned: {},
    total_saved: {},
    total_withdrawn: {},
  });
  mocks.monthly.mockReset().mockResolvedValue({ lines: [] });
});
afterEach(() => window.history.replaceState(null, "", "/"));

describe("DashboardPanel with the redesign switch", () => {
  it("off (default): today's summary, no 'Más detalles', 36px icon buttons", async () => {
    render(<DashboardPanel open onClose={() => {}} />);
    expect(await screen.findByText("Flujo de caja")).toBeInTheDocument();
    expect(screen.getByText("Excedente acumulado", { selector: "p" }).parentElement?.querySelector("p.text-2xl")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Más detalles" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Ir a una sección" })).toBeNull();
    expect(screen.getByRole("button", { name: "Cerrar resumen" }).className).toContain("h-9 w-9");
    for (const name of ["Resumen", "Movimientos", "Este mes", "Mes pasado", "Todo"]) {
      expect(screen.getByRole("button", { name }).className).not.toContain("min-h-11");
    }
  });

  it("?nuevo=1: the new summary, and 44px touch targets on view/period/refresh/close", async () => {
    window.history.replaceState(null, "", "/?nuevo=1");
    render(<DashboardPanel open onClose={() => {}} />);
    expect(await screen.findByRole("button", { name: "Más detalles" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Ir a una sección" })).toBeInTheDocument();
    expect(screen.getByText(/Tu mes ·/)).toBeInTheDocument();

    for (const name of ["Resumen", "Movimientos", "Este mes", "Mes pasado", "Todo"]) {
      expect(screen.getByRole("button", { name }).className).toContain("min-h-11");
    }
    for (const name of ["Cerrar resumen", "Actualizar resumen"]) {
      expect(screen.getByRole("button", { name }).className).toContain("h-11 w-11");
    }
  });

  it("the choice persists across visits without the param", async () => {
    window.history.replaceState(null, "", "/?nuevo=1");
    const first = render(<DashboardPanel open onClose={() => {}} />);
    await screen.findByRole("button", { name: "Más detalles" });
    first.unmount();
    window.history.replaceState(null, "", "/");
    render(<DashboardPanel open onClose={() => {}} />);
    expect(await screen.findByRole("button", { name: "Más detalles" })).toBeInTheDocument();
  });

  it("?nuevo=0 brings the old summary back", async () => {
    window.localStorage.setItem("safi:newDesign", "1");
    window.history.replaceState(null, "", "/?nuevo=0");
    render(<DashboardPanel open onClose={() => {}} />);
    expect(await screen.findByText("Flujo de caja")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Más detalles" })).toBeNull();
  });
});
