import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type {
  CardPaymentsList,
  GoalContributionsList,
  Transaction,
} from "@/lib/types";

import { MovementsList } from "./MovementsList";

function tx(over: Partial<Transaction> = {}): Transaction {
  return {
    id: "t1",
    amount: "50000",
    description: "Consulta médica",
    transaction_type: "expense",
    category: "salud",
    payment_method: "efectivo",
    card_id: null,
    transaction_date: "2026-06-10",
    budget_date: "2026-06-10",
    created_at: "2026-06-10T00:00:00Z",
    ...over,
  };
}

const payments: CardPaymentsList = {
  payments: [{ card_name: "Nu", amount: "4599784", payment_date: "2026-06-01" }],
  total: "4599784",
};

const contributions: GoalContributionsList = {
  contributions: [
    { goal_name: "Viaje a Japón", amount: "150000", contribution_date: "2026-06-05" },
  ],
  total: "150000",
};

describe("MovementsList", () => {
  it("lists card payments as movements", () => {
    render(
      <MovementsList
        transactions={[tx()]}
        cards={null}
        payments={payments}
        contributions={null}
      />,
    );
    expect(screen.getByText("Pago a Nu")).toBeInTheDocument();
    expect(screen.getByText("Consulta médica")).toBeInTheDocument();
  });

  it("keeps card payments under the Efectivo filter", async () => {
    render(
      <MovementsList
        transactions={[tx()]}
        cards={null}
        payments={payments}
        contributions={null}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Efectivo/i }));
    // Paying a card is money out of pocket → still shown under Efectivo.
    expect(screen.getByText("Pago a Nu")).toBeInTheDocument();
  });

  it("lists a goal contribution as an 'Aporte a <meta>' outflow", () => {
    render(
      <MovementsList
        transactions={[tx()]}
        cards={null}
        payments={null}
        contributions={contributions}
      />,
    );
    expect(screen.getByText("Aporte a Viaje a Japón")).toBeInTheDocument();
    // Shown as a negative outflow (leaves the pocket like cash); the amount row
    // carries the "negative" tone. Assert on the value substring, not the glyph.
    const amount = screen.getByText(/150,000/);
    expect(amount.className).toContain("text-negative");
  });

  it("lists a negative goal contribution as a 'Retiro de <meta>' inflow", () => {
    const withdrawal: GoalContributionsList = {
      contributions: [
        { goal_name: "Fondo de emergencia", amount: "-100000", contribution_date: "2026-06-08" },
      ],
      total: "-100000",
    };
    render(
      <MovementsList
        transactions={[tx()]}
        cards={null}
        payments={null}
        contributions={withdrawal}
      />,
    );
    // A withdrawal returns money to disponible → shown as a positive inflow.
    expect(screen.getByText("Retiro de Fondo de emergencia")).toBeInTheDocument();
    const amount = screen.getByText(/100,000/);
    expect(amount.className).toContain("text-positive");
    expect(amount.textContent).toContain("+");
  });

  it("keeps goal contributions under the Efectivo filter", async () => {
    render(
      <MovementsList
        transactions={[tx()]}
        cards={null}
        payments={null}
        contributions={contributions}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Efectivo/i }));
    // A goal contribution is money out of pocket → still shown under Efectivo.
    expect(screen.getByText("Aporte a Viaje a Japón")).toBeInTheDocument();
  });
});
