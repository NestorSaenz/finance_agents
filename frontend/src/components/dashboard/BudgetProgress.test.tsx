import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CurrencyProvider } from "@/context/CurrencyContext";
import type { BudgetStatusItem, BudgetStatusList, Transaction } from "@/lib/types";

import { BudgetProgress } from "./BudgetProgress";

function budgetItem(over: Partial<BudgetStatusItem> = {}): BudgetStatusItem {
  return {
    budget: { id: "b1", name: "Tope de Venezuela", category: "venezuela", amount: "1300000" },
    spent: "238290",
    remaining: "1061710",
    percentage: 18,
    alert_triggered: false,
    period_start: "2026-09-01",
    period_end: "2026-09-30",
    ...over,
  };
}

function list(statuses: BudgetStatusItem[]): BudgetStatusList {
  return { statuses, total_budgeted: "0", total_spent: "0" };
}

function expenseTx(over: Partial<Transaction> = {}): Transaction {
  return {
    id: "v1",
    amount: "238290",
    description: "Merca Facil",
    transaction_type: "expense",
    category: "venezuela",
    payment_method: "credito",
    card_id: null,
    transaction_date: "2026-07-28",
    budget_date: "2026-09-02",
    recurring_id: null,
    created_at: "2026-07-28T00:00:00Z",
    ...over,
  };
}

function renderBudgets(props: Partial<Parameters<typeof BudgetProgress>[0]> = {}) {
  return render(
    <CurrencyProvider currency="COP">
      <BudgetProgress data={list([budgetItem()])} transactions={[]} {...props} />
    </CurrencyProvider>,
  );
}

describe("BudgetProgress", () => {
  it("expands a category to list the expenses behind its 'spent' total", async () => {
    renderBudgets({ transactions: [expenseTx()] });

    expect(screen.queryByRole("region", { name: /Movimientos de Venezuela/i })).toBeNull();

    const toggle = screen.getByRole("button", { name: "Ver movimientos de Venezuela" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const region = await screen.findByRole("region", { name: /Movimientos de Venezuela/i });
    expect(region).toHaveTextContent("Merca Facil");
  });

  it("does not make a category expandable when nothing composes it", () => {
    renderBudgets({ transactions: [] });

    expect(screen.getByText("Venezuela")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Ver movimientos/i }),
    ).toBeNull();
  });

  it("keeps a single category open at a time (accordion)", async () => {
    const statuses = list([
      budgetItem(),
      budgetItem({
        budget: { id: "b2", name: "Tope de Mercado", category: "mercado", amount: "500000" },
        spent: "100000",
      }),
    ]);
    render(
      <CurrencyProvider currency="COP">
        <BudgetProgress
          data={statuses}
          transactions={[
            expenseTx(),
            expenseTx({ id: "m1", description: "Euro Supermercado", category: "mercado" }),
          ]}
        />
      </CurrencyProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Ver movimientos de Venezuela" }));
    expect(screen.getByText("Merca Facil")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ver movimientos de Mercado" }));
    expect(screen.getByText("Euro Supermercado")).toBeInTheDocument();
    expect(screen.queryByText("Merca Facil")).toBeNull();
  });

  it("shows the real purchase date, not the budget period, for a divergent row", async () => {
    // The Venezuela bug: bought in July, paid (and budgeted) in September.
    renderBudgets({ transactions: [expenseTx()] });

    await userEvent.click(screen.getByRole("button", { name: "Ver movimientos de Venezuela" }));

    expect(screen.getByText(/28 jul/i)).toBeInTheDocument();
  });

  it("excludes recurring occurrences from a category's detail", async () => {
    // A fixed bill (e.g. Netflix) never counts toward a budget's spent (mig.
    // 014); it must not appear in the detail list either.
    renderBudgets({
      transactions: [
        expenseTx(),
        expenseTx({ id: "rec1", description: "Netflix", recurring_id: "r-1" }),
      ],
    });

    await userEvent.click(screen.getByRole("button", { name: "Ver movimientos de Venezuela" }));

    expect(screen.getByText("Merca Facil")).toBeInTheDocument();
    expect(screen.queryByText("Netflix")).toBeNull();
  });

  it("flags when the listed rows don't reconcile with the bar's total", async () => {
    // spent=500000 but only 238290 of matching rows were fetched (e.g. capped) —
    // must say so rather than silently show a smaller, disagreeing total.
    renderBudgets({
      transactions: [expenseTx()],
      data: list([budgetItem({ spent: "500000" })]),
    });

    await userEvent.click(screen.getByRole("button", { name: "Ver movimientos de Venezuela" }));

    expect(
      screen.getByText(/No pudimos detallar todos los movimientos/i),
    ).toBeInTheDocument();
  });

  it("expands an overall (no-category) budget to all expense rows", async () => {
    const statuses = list([
      budgetItem({
        budget: { id: "b3", name: "Tope general", category: null, amount: "5000000" },
        spent: "338290",
      }),
    ]);
    render(
      <CurrencyProvider currency="COP">
        <BudgetProgress
          data={statuses}
          transactions={[
            expenseTx(),
            expenseTx({ id: "m1", description: "Euro Supermercado", category: "mercado", amount: "100000" }),
          ]}
        />
      </CurrencyProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Ver movimientos de Tope general" }));

    expect(screen.getByText("Merca Facil")).toBeInTheDocument();
    expect(screen.getByText("Euro Supermercado")).toBeInTheDocument();
  });

  it("renders the empty state when there are no budgets", () => {
    render(
      <CurrencyProvider currency="COP">
        <BudgetProgress data={list([])} transactions={[]} />
      </CurrencyProvider>,
    );
    expect(screen.getByText(/Aún no tienes topes definidos/i)).toBeInTheDocument();
  });
});
