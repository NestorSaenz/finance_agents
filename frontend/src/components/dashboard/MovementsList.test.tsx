import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { CardPaymentsList, Transaction } from "@/lib/types";

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

describe("MovementsList", () => {
  it("lists card payments as movements", () => {
    render(<MovementsList transactions={[tx()]} cards={null} payments={payments} />);
    expect(screen.getByText("Pago a Nu")).toBeInTheDocument();
    expect(screen.getByText("Consulta médica")).toBeInTheDocument();
  });

  it("keeps card payments under the Efectivo filter", async () => {
    render(<MovementsList transactions={[tx()]} cards={null} payments={payments} />);
    await userEvent.click(screen.getByRole("button", { name: /Efectivo/i }));
    // Paying a card is money out of pocket → still shown under Efectivo.
    expect(screen.getByText("Pago a Nu")).toBeInTheDocument();
  });
});
