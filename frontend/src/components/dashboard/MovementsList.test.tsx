import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { formatMoney } from "@/lib/format";
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
    const amount = screen.getByText(/150[.,]000/, { selector: "li p" });
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

    it("headline = expenses + payments + saved; breakdown lists the non-zero parts; withdrawals apart", async () => {
      render(
        <MovementsList
          transactions={[tx({ amount: "100000" })]}
          cards={null}
          payments={pay}
          contributions={aporte}
        />,
      );
      await openCash();
      // 100.000 cash + 300.000 payment + 500.000 saved = 900.000 (gross; the
      // 2.000.000 withdrawal is NOT netted in).
      const header = screen.getByText(/movimiento\(s\)/);
      expect(header.textContent).toContain(`salió de tu caja ${formatMoney(900000)}`);
      const breakdown = screen.getByText(/^Gastos en efectivo/, { selector: "p" });
      expect(breakdown.textContent).toMatch(
        /Gastos en efectivo\D*100[.,]000\D*Pagos a tarjetas\D*300[.,]000\D*Apartado para metas\D*500[.,]000/,
      );
      const back = screen.getByText(/Volvió de tus metas/);
      expect(back.textContent).toMatch(/\+\D*2[.,]000[.,]000/);
      expect(back.textContent).toContain(`+${formatMoney(2000000)}`);
      expect(
        screen.getByText(
          "Lo apartado para metas es ahorro: sigue siendo tuyo, pero ya no está libre.",
        ),
      ).toBeInTheDocument();
      expect(screen.queryByText(/Metas \(no es gasto\)/)).not.toBeInTheDocument();
    });

    it("shows no goal lines or notes without goal movements", async () => {
      render(
        <MovementsList transactions={[tx()]} cards={null} payments={pay} contributions={null} />,
      );
      await openCash();
      expect(screen.queryByText(/Volvió de tus metas/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Apartado para metas/)).not.toBeInTheDocument();
      expect(screen.queryByText(/ahorro: sigue siendo tuyo/)).not.toBeInTheDocument();
    });

    it("with only a withdrawal: headline unchanged, only 'Volvió de tus metas'", async () => {
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
      expect(screen.getByText(/Volvió de tus metas/).textContent).toMatch(/100[.,]000/);
      expect(screen.queryByText(/Apartado para metas/)).not.toBeInTheDocument();
      expect(screen.getByText(/movimiento\(s\)/).textContent).toMatch(
        /salió de tu caja\D*50[.,]000/,
      );
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
      expect(screen.getByText(/movimiento\(s\)/).textContent).toMatch(/salió de tu caja\D*\$?\s*20[.,]000/);
    });

    it("hides the goal lines when switching to a card chip", async () => {
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
      expect(screen.getByText(/Volvió de tus metas/)).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /Nu/ }));
      expect(screen.queryByText(/Volvió de tus metas/)).not.toBeInTheDocument();
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

    it("'Todas' gastado = consumo + aportes from the cutoff; retiros and older aportes do not add", () => {
      const rows: GoalContributionsList = {
        contributions: [
          { goal_name: "Viaje", amount: "500000", contribution_date: "2026-06-05" },
          { goal_name: "Viaje", amount: "-2000000", contribution_date: "2026-06-06" },
          { goal_name: "Viejo", amount: "900000", contribution_date: "2026-05-20" },
        ],
        total: "0",
      };
      render(
        <MovementsList
          transactions={[tx({ amount: "50000" })]}
          cards={null}
          payments={pay}
          contributions={rows}
          goalSpendingFrom="2026-06-01"
        />,
      );
      // 50.000 consumo + 500.000 aporte; the retiro, the payment and the
      // pre-cutoff aporte do not add.
      expect(headerFigure()).toBe(550000);
      const breakdown = screen.getByText(/^consumo/, { selector: "p" });
      expect(breakdown.textContent).toContain(formatMoney(50000));
      expect(breakdown.textContent).toContain(formatMoney(500000));
      expect(screen.getByText(/Incluye lo apartado a metas/)).toBeInTheDocument();
    });

    it("'Todas' before the cutoff (or without one) keeps gastado = consumo", () => {
      render(
        <MovementsList transactions={[tx()]} cards={null} payments={null} contributions={aporte} />,
      );
      expect(headerFigure()).toBe(50000);
      expect(screen.queryByText(/^consumo/, { selector: "p" })).not.toBeInTheDocument();
      expect(screen.queryByText(/Además apartaste/)).not.toBeInTheDocument();
    });

    it("'Todo' crossing the cutoff counts only aportes on/after it; absent cutoff counts none", () => {
      const rows: GoalContributionsList = {
        contributions: [
          { goal_name: "Julio", amount: "300000", contribution_date: "2026-07-10" },
          { goal_name: "Oct", amount: "200000", contribution_date: "2026-10-10" },
          { goal_name: "Julio", amount: "-100000", contribution_date: "2026-07-12" },
        ],
        total: "400000",
      };
      const { unmount } = render(
        <MovementsList
          transactions={[tx({ amount: "50000" })]}
          cards={null}
          payments={null}
          contributions={rows}
          goalSpendingFrom="2026-10-01"
        />,
      );
      expect(headerFigure()).toBe(250000); // 50.000 + only the October aporte
      unmount();
      render(
        <MovementsList
          transactions={[tx({ amount: "50000" })]}
          cards={null}
          payments={null}
          contributions={rows}
          goalSpendingFrom={undefined}
        />,
      );
      expect(headerFigure()).toBe(50000);
    });

    it("Efectivo and card chips keep their values when aportes count as gasto", async () => {
      render(
        <MovementsList
          transactions={[
            tx({ id: "k", amount: "250000", payment_method: "credito", card_id: "c1" }),
            tx({ id: "a", amount: "100000" }),
          ]}
          cards={nuCards}
          payments={pay}
          contributions={aporte}
          goalSpendingFrom="2026-06-01"
        />,
      );
      await openCash();
      // cash 100.000 + payments 300.000 + saved 500.000 (the Flujo de caja line by line).
      expect(headerFigure()).toBe(900000);
      await userEvent.click(screen.getByRole("button", { name: /Nu/ }));
      expect(headerFigure()).toBe(250000);
    });

    it("Efectivo breakdown lists the two parts and the payment note", async () => {
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
        /salió de tu caja\D*400[.,]000/,
      );
      const line = screen.getByText(/^Gastos en efectivo/, { selector: "p" });
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
        <MovementsList transactions={[tx()]} cards={null} payments={null} contributions={null} />,
      );
      await openCash();
      expect(screen.queryByText(/^Gastos en efectivo/, { selector: "p" })).not.toBeInTheDocument();
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
      // Only payments: no breakdown line, but the note stays.
      expect(screen.queryByText(/^Gastos en efectivo/, { selector: "p" })).not.toBeInTheDocument();
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
            goalSaved={500000}
            goalWithdrawn={2000000}
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

      // (b) Efectivo header == Resumen Flujo de caja lines, line by line:
      // Efectivo + Pagos a tarjetas + Apartado para metas (withdrawals apart).
      const dd = (label: string) =>
        parse(screen.getByText(label, { selector: "dt" }).nextElementSibling?.textContent);
      await openCash();
      expect(headerFigure()).toBe(
        dd("Efectivo") + dd("Pagos a tarjetas") + dd("Apartado para metas"),
      );
      expect(headerFigure()).toBe(2200000);
      expect(screen.getByText(/Volvió de tus metas/).textContent).toMatch(/2[.,]000[.,]000/);
      expect(dd("Retirado de metas")).toBe(2000000);

      // (c) Efectivo cash part + Nu chip gastado == Todas gastado.
      const breakdown = screen.getByText(/^Gastos en efectivo/, { selector: "p" });
      const efectivoSpan = within(breakdown).getAllByText(/\d/)[0];
      await userEvent.click(screen.getByRole("button", { name: /Nu/ }));
      const nu = headerFigure();
      expect(parse(efectivoSpan.textContent) + nu).toBe(todas);
    });
  });
});
