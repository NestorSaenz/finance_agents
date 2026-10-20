import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type {
  CardPaymentsList,
  CreditCardStatusList,
  GoalContributionsList,
  SpendingSummary,
  Transaction,
} from "@/lib/types";

import { MovementsList } from "./MovementsList";
import { SummaryContent } from "./SummaryContent";

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
    const amount = screen.getByText(/150[.,]000/);
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
    const amount = screen.getByText(/100[.,]000/);
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

  describe("Efectivo filter totals", () => {
    const aporte: GoalContributionsList = {
      contributions: [
        { goal_name: "Viaje", amount: "500000", contribution_date: "2026-06-05" },
        { goal_name: "Emergencia", amount: "-2000000", contribution_date: "2026-06-06" },
      ],
      total: "-1500000",
    };
    const pay: CardPaymentsList = {
      payments: [{ card_name: "Nu", amount: "300000", payment_date: "2026-06-01" }],
      total: "300000",
    };
    const nuCards: CreditCardStatusList = {
      cards: [
        {
          card: { id: "c1", name: "Nu" },
          statement_start: null,
        },
      ],
    } as unknown as CreditCardStatusList;

    async function openCash() {
      await userEvent.click(screen.getByRole("button", { name: /Efectivo/i }));
    }

    it("excludes goal movements from the pocket total and shows both gross goal amounts", async () => {
      render(
        <MovementsList
          transactions={[tx({ amount: "100000" })]}
          cards={null}
          payments={pay}
          contributions={aporte}
        />,
      );
      await openCash();
      // 100.000 cash + 300.000 payment = 400.000; goals are left out.
      const header = screen.getByText(/movimiento\(s\)/);
      expect(header.textContent).toMatch(/salió de tu bolsillo\D*\$?\s*400[.,]000/);
      const goalLine = screen.getByText(/Metas \(no es gasto\)/);
      expect(goalLine.textContent).toMatch(/guardaste\s*\$?\s*500[.,]000/);
      expect(goalLine.textContent).toMatch(/retiraste\s*\$?\s*2[.,]000[.,]000/);
    });

    it("shows no Metas line without goal movements", async () => {
      render(
        <MovementsList transactions={[tx()]} cards={null} payments={pay} contributions={null} />,
      );
      await openCash();
      expect(screen.queryByText(/Metas \(no es gasto\)/)).not.toBeInTheDocument();
    });

    it("shows only 'retiraste' when there is just a withdrawal", async () => {
      const onlyWithdrawal: GoalContributionsList = {
        contributions: [
          { goal_name: "Emergencia", amount: "-100000", contribution_date: "2026-06-06" },
        ],
        total: "-100000",
      };
      render(
        <MovementsList
          transactions={[tx({ amount: "50000" })]}
          cards={null}
          payments={null}
          contributions={onlyWithdrawal}
        />,
      );
      await openCash();
      const goalLine = screen.getByText(/Metas \(no es gasto\)/);
      expect(goalLine.textContent).toMatch(/retiraste/);
      expect(goalLine.textContent).not.toMatch(/guardaste/);
      expect(screen.getByText(/movimiento\(s\)/).textContent).toMatch(/salió de tu bolsillo\D*\$?\s*50[.,]000/);
    });

    it("treats untagged card-less expenses as cash; ignores credit and income", async () => {
      render(
        <MovementsList
          transactions={[
            tx({ id: "u", description: "Sin etiqueta", amount: "20000", payment_method: null }),
            tx({
              id: "k",
              description: "Compra crédito",
              amount: "900000",
              payment_method: "credito",
              card_id: "c1",
            }),
            tx({
              id: "i",
              description: "Sueldo",
              amount: "7000000",
              transaction_type: "income",
              payment_method: null,
            }),
          ]}
          cards={nuCards}
          payments={null}
          contributions={null}
        />,
      );
      await openCash();
      expect(screen.getByText("Sin etiqueta")).toBeInTheDocument();
      expect(screen.queryByText("Compra crédito")).not.toBeInTheDocument();
      expect(screen.getByText(/movimiento\(s\)/).textContent).toMatch(/salió de tu bolsillo\D*\$?\s*20[.,]000/);
    });

    it("hides the Metas line when switching to a card chip", async () => {
      render(
        <MovementsList
          transactions={[
            tx({ id: "k", description: "Compra crédito", payment_method: "credito", card_id: "c1" }),
          ]}
          cards={nuCards}
          payments={null}
          contributions={aporte}
        />,
      );
      await openCash();
      expect(screen.getByText(/Metas \(no es gasto\)/)).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /Nu/ }));
      expect(screen.queryByText(/Metas \(no es gasto\)/)).not.toBeInTheDocument();
    });

    it("'Todas' shows gastado = Σ expenses (no income, payments or goals) and the note", () => {
      render(
        <MovementsList
          transactions={[
            tx({ id: "a", amount: "100000" }),
            tx({ id: "k", amount: "250000", payment_method: "credito", card_id: "c1" }),
            tx({ id: "i", amount: "7000000", transaction_type: "income", payment_method: null }),
          ]}
          cards={nuCards}
          payments={pay}
          contributions={aporte}
        />,
      );
      expect(screen.getByText(/movimiento\(s\)/).textContent).toMatch(/gastado\s*\$?\s*350[.,]000/);
      expect(
        screen.getByText(
          "Igual a «Gastos» del Resumen. No incluye pagos a tarjetas ni movimientos de metas.",
        ),
      ).toBeInTheDocument();
    });

    const parse = (text: string | null | undefined): number =>
      Number((text ?? "").replace(/\D/g, ""));
    /** The figure in the header line (the bold amount span). */
    const headerFigure = () =>
      parse(screen.getByText(/movimiento\(s\)/).querySelector("span")?.textContent);

    it("Efectivo shows the 'salió de tu bolsillo' header, the two-part breakdown and the payment note", async () => {
      render(
        <MovementsList
          transactions={[tx({ amount: "100000" })]}
          cards={null}
          payments={pay}
          contributions={null}
        />,
      );
      await openCash();
      expect(screen.getByText(/movimiento\(s\)/).textContent).toMatch(
        /salió de tu bolsillo\D*400[.,]000/,
      );
      const line = screen.getByText(/^Efectivo/, { selector: "p" });
      const [cashPart, paidPart] = within(line).getAllByText(/\d/);
      expect(parse(cashPart.textContent)).toBe(100000);
      expect(parse(paidPart.textContent)).toBe(300000);
      expect(parse(cashPart.textContent) + parse(paidPart.textContent)).toBe(headerFigure());
      expect(
        screen.getByText(
          "Los pagos a tarjetas cubren compras con tarjeta (normalmente de meses anteriores); por eso no se suman a lo gastado.",
        ),
      ).toBeInTheDocument();
    });

    it("hides the breakdown when only one part is non-zero, keeping the note for payments", async () => {
      const { unmount } = render(
        <MovementsList transactions={[tx()]} cards={null} payments={null} contributions={aporte} />,
      );
      await openCash();
      expect(screen.queryByText(/^Efectivo/, { selector: "p" })).not.toBeInTheDocument();
      expect(screen.queryByText(/por eso no se suman/)).not.toBeInTheDocument();
      unmount();

      render(
        <MovementsList
          transactions={[tx({ payment_method: "credito", card_id: "c1" })]}
          cards={nuCards}
          payments={pay}
          contributions={null}
        />,
      );
      await openCash();
      // Only payments: no "Efectivo $X + pagos…" line, but the note stays.
      expect(screen.queryByText(/^Efectivo/, { selector: "p" })).not.toBeInTheDocument();
      expect(screen.getByText(/por eso no se suman/)).toBeInTheDocument();
    });

    it("a credito tx without card_id is not in Efectivo but counts in 'Todas' gastado", async () => {
      render(
        <MovementsList
          transactions={[
            tx({ id: "a", amount: "100000" }),
            tx({ id: "n", description: "Crédito huérfano", amount: "70000", payment_method: "credito" }),
          ]}
          cards={null}
          payments={null}
          contributions={null}
        />,
      );
      expect(headerFigure()).toBe(170000);
      await openCash();
      expect(screen.queryByText("Crédito huérfano")).not.toBeInTheDocument();
      expect(headerFigure()).toBe(100000);
    });

    it("per-card chip keeps 'gastado' and swaps the helper lines", async () => {
      render(
        <MovementsList
          transactions={[
            tx({ id: "k", amount: "250000", payment_method: "credito", card_id: "c1" }),
            tx({ id: "a", amount: "100000" }),
          ]}
          cards={nuCards}
          payments={pay}
          contributions={null}
        />,
      );
      await userEvent.click(screen.getByRole("button", { name: /Nu/ }));
      expect(screen.getByText(/movimiento\(s\)/).textContent).toMatch(/gastado\D*250[.,]000/);
      expect(screen.queryByText(/Igual a «Gastos»/)).not.toBeInTheDocument();
      expect(screen.queryByText(/por eso no se suman/)).not.toBeInTheDocument();
      await openCash();
      expect(screen.getByText(/por eso no se suman/)).toBeInTheDocument();
      expect(screen.queryByText(/Igual a «Gastos»/)).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Todas" }));
      expect(screen.getByText(/Igual a «Gastos»/)).toBeInTheDocument();
      expect(screen.queryByText(/por eso no se suman/)).not.toBeInTheDocument();
    });

    it("one fixture reconciles the Resumen with Todas, Efectivo and card chips", async () => {
      // Every expense here is cash or linked to a card in the fixture. A 'credito'
      // tx without card_id appears in no chip, so this identity is not universal.
      const txs = [
        tx({ id: "a", amount: "1000000" }),
        tx({ id: "b", amount: "400000", payment_method: null }),
        tx({ id: "k", amount: "250000", payment_method: "credito", card_id: "c1" }),
      ];
      const summary: SpendingSummary = {
        period: "2026-06",
        total_income: "2000000",
        total_expenses: "1650000",
        balance: "350000",
        by_category: [],
        credit_expenses: "250000",
        cash_expenses: "1400000",
      };
      render(
        <>
          <SummaryContent
            summary={summary}
            budget={null}
            budgetTransactions={[]}
            profile={null}
            goals={[]}
            goalContributions={-1500000}
            accumulatedSurplus={0}
            cards={null}
            payments={pay}
            transactions={txs}
            recurring={[]}
            period="2026-06"
          />
          <MovementsList transactions={txs} cards={nuCards} payments={pay} contributions={aporte} />
        </>,
      );
      // (a) Todas gastado == Resumen "Gastos" card.
      const gastosCard = parse(
        screen.getByText("Gastos").parentElement?.querySelector("p:nth-of-type(2)")?.textContent,
      );
      const todas = headerFigure();
      expect(todas).toBe(1650000);
      expect(todas).toBe(gastosCard);

      // (b) Efectivo header == Resumen Flujo de caja "Efectivo" + "Pagos a tarjetas".
      const dd = (label: string) =>
        parse(screen.getByText(label, { selector: "dt" }).nextElementSibling?.textContent);
      await openCash();
      expect(headerFigure()).toBe(dd("Efectivo") + dd("Pagos a tarjetas"));

      // (c) Efectivo cash part + Nu chip gastado == Todas gastado.
      const breakdown = screen.getByText(/^Efectivo/, { selector: "p" });
      const efectivoSpan = within(breakdown).getAllByText(/\d/)[0];
      await userEvent.click(screen.getByRole("button", { name: /Nu/ }));
      const nu = headerFigure();
      expect(parse(efectivoSpan.textContent) + nu).toBe(todas);
    });
  });
});
