import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CurrencyProvider } from "@/context/CurrencyContext";
import type {
  CardPaymentItem,
  CreditCardStatusItem,
  CreditCardStatusList,
  Transaction,
} from "@/lib/types";

import { CardStatus } from "./CardStatus";

function cardItem(over: Partial<CreditCardStatusItem> = {}): CreditCardStatusItem {
  return {
    card: {
      id: "card-1",
      name: "Visa BBVA",
      credit_limit: "5000000",
      cutoff_day: 15,
      payment_day: 5,
    },
    cycle_start: "2026-07-16",
    cycle_end: "2026-08-15",
    spent_cycle: "200000",
    balance: "500000",
    available: "4500000",
    utilization: 10,
    next_payment_date: "2026-08-05",
    ...over,
  };
}

function list(cards: CreditCardStatusItem[]): CreditCardStatusList {
  return { cards, total_limit: "0", total_balance: "0", total_available: "0" };
}

function charge(over: Partial<Transaction> = {}): Transaction {
  return {
    id: "tx-1",
    amount: "304139",
    description: "Euro Arkadia",
    transaction_type: "expense",
    category: "mercado",
    payment_method: "credito",
    card_id: "card-1",
    transaction_date: "2026-07-25",
    budget_date: "2026-08-05",
    created_at: "2026-07-25T00:00:00Z",
    ...over,
  };
}

function payment(over: Partial<CardPaymentItem> = {}): CardPaymentItem {
  return {
    card_id: "card-1",
    card_name: "Visa BBVA",
    amount: "1500000",
    payment_date: "2026-07-05",
    ...over,
  };
}

function renderCards(props: Partial<Parameters<typeof CardStatus>[0]> = {}) {
  return render(
    <CurrencyProvider currency="COP">
      <CardStatus
        data={list([cardItem()])}
        transactions={[]}
        payments={[]}
        period="2026-07"
        {...props}
      />
    </CurrencyProvider>,
  );
}

describe("CardStatus", () => {
  it("expands a card's mini-statement (charges + payments) on click", async () => {
    renderCards({ transactions: [charge()], payments: [payment()] });

    // Collapsed: the statement region isn't rendered yet.
    expect(screen.queryByRole("region", { name: /Movimientos de Visa BBVA/i })).toBeNull();

    const toggle = screen.getByRole("button", { name: "Ver movimientos de Visa BBVA" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const region = await screen.findByRole("region", { name: /Movimientos de Visa BBVA/i });
    // Charge + payment both listed inside the statement.
    expect(screen.getByText("Euro Arkadia")).toBeInTheDocument();
    expect(screen.getByText("Pago a la tarjeta")).toBeInTheDocument();
    // The month-labelled charges heading is present.
    expect(region).toHaveTextContent(/Compras de julio de 2026/i);
    expect(region).toHaveTextContent(/Pagos/);
  });

  it("does not make a card expandable when it has no charges or payments", () => {
    renderCards();

    // The card still renders, but there is no toggle button and no chevron.
    expect(screen.getByText("Visa BBVA")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Ver movimientos/i }),
    ).toBeNull();
  });

  it("keeps a single card open at a time (accordion)", async () => {
    const cards = list([
      cardItem(),
      cardItem({ card: { id: "card-2", name: "Nu", credit_limit: "3000000", cutoff_day: 20, payment_day: 10 } }),
    ]);
    render(
      <CurrencyProvider currency="COP">
        <CardStatus
          data={cards}
          transactions={[charge(), charge({ id: "tx-2", description: "Rappi", card_id: "card-2" })]}
          payments={[]}
          period="2026-07"
        />
      </CurrencyProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Ver movimientos de Visa BBVA" }));
    expect(screen.getByText("Euro Arkadia")).toBeInTheDocument();

    // Opening the second closes the first.
    await userEvent.click(screen.getByRole("button", { name: "Ver movimientos de Nu" }));
    expect(screen.getByText("Rappi")).toBeInTheDocument();
    expect(screen.queryByText("Euro Arkadia")).toBeNull();
  });
});
