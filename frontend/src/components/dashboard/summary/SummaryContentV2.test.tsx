import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { formatMoney } from "@/lib/format";
import type {
  BudgetStatusList,
  GoalPlanStatusList,
  Recurring,
  SpendingSummary,
  UserProfile,
} from "@/lib/types";

import { SummaryContent } from "../SummaryContent";
import { SummaryContentV2 } from "./SummaryContentV2";

// Same fixtures as SummaryContent.test.tsx (kept local so that file stays untouched).
const splitSpy = vi.hoisted(() => vi.fn());
vi.mock("../PaymentSplit", () => ({
  PaymentSplit: (props: { totalExpenses: number }) => {
    splitSpy(props);
    return <p>Cómo pagas</p>;
  },
}));

const money = (v: number) => formatMoney(v);
const digits = (el: Element | null | undefined) => Number((el?.textContent ?? "").replace(/\D/g, ""));

function summary(over: Partial<SpendingSummary> = {}): SpendingSummary {
  return {
    period: "este_mes",
    total_income: "10000000",
    total_expenses: "1000000",
    balance: "9000000",
    by_category: [{ category: "restaurantes", amount: "1000000", percentage: 100 }],
    credit_expenses: "0",
    cash_expenses: "1000000",
    goal_saved: "500000",
    total_spent: "1500000",
    goal_withdrawn: "200000",
    goal_spending_from: "2026-10-01",
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
const plan = (remaining: string): GoalPlanStatusList => ({
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
    },
  ],
  total_planned: { COP: "500000" },
  total_effective_planned: { COP: "500000" },
  total_saved: { COP: "0" },
  total_withdrawn: { COP: "0" },
});
const topes: BudgetStatusList = {
  statuses: [
    {
      budget: { id: "b1", name: "Mercado", category: "mercado", amount: "2000000" },
      spent: "0",
      remaining: "2000000",
      percentage: 0,
      alert_triggered: false,
      period_start: "2026-10-01",
      period_end: "2026-10-31",
    },
  ],
  total_budgeted: "2000000",
  total_spent: "0",
};
const recurring: Recurring[] = [
  {
    id: "r1",
    description: "Netflix",
    amount: "16900",
    transaction_type: "expense",
    category: null,
    payment_method: null,
    day_of_month: 3,
    next_run_date: "2026-11-03",
    active: true,
  },
];

type Props = React.ComponentProps<typeof SummaryContent>;
const base: Props = {
  summary: summary(),
  budget: topes,
  budgetTransactions: [],
  profile: PROFILE,
  goals: [{ id: "g", name: "Japón", target_amount: "8000000", current_amount: "1200000", status: "active" }],
  goalSaved: 500000,
  goalWithdrawn: 200000,
  accumulatedSurplus: 777000,
  cards: null,
  payments: {
    payments: [{ card_id: "c", card_name: "Nu", amount: "300000", payment_date: "2026-10-05" }],
    total: "300000",
  },
  transactions: [],
  recurring,
  period: "este_mes",
  planStatus: plan("500000"),
};

const dd = (label: string) => digits(screen.getByText(label, { selector: "dt" }).nextElementSibling);
// The lead card is a named region; read its stats by role, not by long texts.
const stat = (label: string) =>
  digits(
    within(screen.getByRole("region", { name: "Cifra principal del resumen" })).getByText(label, {
      selector: "p",
    }).nextElementSibling,
  );

describe("SummaryContentV2 reconciles with SummaryContent (same data, same figures)", () => {
  it("Ingresos, Gastos, Balance, Flujo de caja, Excedente, plan and topes match", () => {
    // Old view.
    const old = render(<SummaryContent {...base} />);
    const oldFigures = {
      ingresos: digits(screen.getByText("Ingresos", { selector: "p" }).nextElementSibling),
      gastos: digits(screen.getByText("Gastos", { selector: "p" }).nextElementSibling),
      balance: digits(screen.getByText("Balance", { selector: "p" }).nextElementSibling),
      efectivo: dd("Efectivo"),
      pagos: dd("Pagos a tarjetas"),
      teSobro: dd("Te sobró"),
      apartado: dd("Apartado para metas"),
      cajaFinal: dd("Caja final del mes"),
      excedente: digits(screen.getByText("Excedente acumulado").nextElementSibling),
      porAportar: digits(screen.getByText(/Por aportar a tus metas este mes/)),
      topes: digits(screen.getByText(/Tus topes suman/)),
    };
    old.unmount();

    // New view.
    render(<SummaryContentV2 {...base} />);
    expect(stat("Ingresos")).toBe(oldFigures.ingresos);
    expect(stat("Gastos")).toBe(oldFigures.gastos);
    expect(stat("Balance")).toBe(oldFigures.balance);
    expect(dd("Efectivo")).toBe(oldFigures.efectivo);
    expect(dd("Pagos a tarjetas")).toBe(oldFigures.pagos);
    expect(dd("Te sobró")).toBe(oldFigures.teSobro);
    expect(dd("Apartado para metas")).toBe(oldFigures.apartado);
    expect(dd("Caja final del mes")).toBe(oldFigures.cajaFinal);
    expect(digits(screen.getByText("Excedente acumulado").nextElementSibling)).toBe(oldFigures.excedente);
    expect(digits(screen.getByText(/Por aportar a tus metas este mes/))).toBe(oldFigures.porAportar);
    expect(digits(screen.getByText(/Tus topes suman/))).toBe(oldFigures.topes);
    // The headline is the final cash (same number as the Flujo de caja line).
    expect(digits(screen.getByText("Tu mes · noviembre").nextElementSibling)).toBe(oldFigures.cajaFinal);
  });

  it("nothing disappears: Recurrentes, Pagos, the split and Gastos por categoría live in 'Más detalles'", async () => {
    render(<SummaryContentV2 {...base} />);
    const toggle = screen.getByRole("button", { name: "Más detalles" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle.className).toContain("min-h-11");
    expect(screen.queryByText("Recurrentes")).toBeNull();
    expect(screen.queryByText("Gastos por categoría (consumo)")).toBeNull();

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Recurrentes")).toBeInTheDocument();
    expect(screen.getByText("Pagos a tarjetas", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("Cómo pagas")).toBeInTheDocument();
    expect(screen.getByText("Gastos por categoría (consumo)")).toBeInTheDocument();
    // PaymentSplit still receives consumo, not total_spent.
    expect(splitSpy).toHaveBeenCalledWith(expect.objectContaining({ totalExpenses: 1000000 }));
  });

  it("keeps the visible notes that change how a figure reads", () => {
    render(<SummaryContentV2 {...base} />);
    expect(screen.getByText("Es un plan: no cuenta como gasto hasta que registres el aporte.")).toBeInTheDocument();
    expect(screen.getByText(/Incluye .* apartados a metas/)).toBeInTheDocument();
    expect(screen.getByText(/Además volvieron/)).toBeInTheDocument();
    // Long definitions are behind an "i".
    expect(screen.getByRole("button", { name: "Qué significa Excedente acumulado" })).toBeInTheDocument();
    expect(screen.queryByText(/Tu plata libre acumulada/)).toBeNull();
  });

  it("past month without topes: the note stays, and no 'Por aportar'", () => {
    render(<SummaryContentV2 {...base} budget={null} period="mes_pasado" />);
    expect(screen.getByText("Los topes se muestran solo para el mes en curso.")).toBeInTheDocument();
    expect(screen.queryByText(/Por aportar a tus metas/)).toBeNull();
  });

  it("jump chips exist only for the sections shown", () => {
    const { unmount } = render(<SummaryContentV2 {...base} />);
    const nav = screen.getByRole("navigation", { name: "Ir a una sección" });
    expect(within(nav).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Flujo",
      "Topes",
      "Metas",
    ]); // no cards -> no "Tarjetas" chip
    expect(within(nav).getByRole("button", { name: "Flujo de caja" })).toBeInTheDocument();
    unmount();
    render(<SummaryContentV2 {...base} goals={[]} budget={null} planStatus={null} />);
    expect(screen.queryByRole("button", { name: "Metas" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Topes" })).toBeNull();
  });

  it("the empty period keeps today's empty message", () => {
    render(
      <SummaryContentV2
        {...base}
        goals={[]}
        summary={summary({ total_income: "0", total_expenses: "0", by_category: [] })}
      />,
    );
    expect(screen.getByText(/Aún no hay movimientos en este período/)).toBeInTheDocument();
  });

  it("'todo' leads with the accumulated surplus (not repeated as a compact card)", () => {
    render(<SummaryContentV2 {...base} period="todo" budget={null} planStatus={null} />);
    expect(screen.getByText("De toda tu historia")).toBeInTheDocument();
    expect(screen.getByText((c) => c.replace(/\s/g, " ") === money(777000).replace(/\s/g, " "), { selector: "p.text-3xl" })).toBeInTheDocument();
    expect(screen.queryByText("Excedente acumulado")).toBeNull();
  });

  it("'todo' has no compact surplus card and no consumption bar", () => {
    render(<SummaryContentV2 {...base} period="todo" budget={null} planStatus={null} />);
    expect(screen.queryByRole("button", { name: "Qué significa Excedente acumulado" })).toBeNull();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("mes pasado with a base income but no logged income shows the spending headline", () => {
    render(
      <SummaryContentV2
        {...base}
        period="mes_pasado"
        budget={null}
        planStatus={null}
        summary={summary({ total_income: "0", goal_saved: undefined, total_spent: undefined })}
      />,
    );
    expect(screen.getByText(/Registra tus ingresos para ver tu caja/)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("jumping to 'Flujo de caja' puts focus on its heading", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    render(<SummaryContentV2 {...base} />);
    await userEvent.click(screen.getByRole("button", { name: "Flujo de caja" }));
    const heading = screen.getByRole("heading", { name: "Flujo de caja" });
    expect(heading).toHaveFocus();
    expect(heading.className).toContain("sr-only");
    expect(heading.className).toContain("focus:outline-none");
    // @ts-expect-error cleanup of the stubbed method
    delete Element.prototype.scrollIntoView;
  });

  it("'Más detalles' holds all four sections once opened", async () => {
    render(<SummaryContentV2 {...base} />);
    await userEvent.click(screen.getByRole("button", { name: "Más detalles" }));
    const region = document.getElementById(
      screen.getByRole("button", { name: "Más detalles" }).getAttribute("aria-controls") ?? "",
    ) as HTMLElement;
    for (const text of ["Recurrentes", "Cómo pagas", "Gastos por categoría (consumo)"]) {
      expect(within(region).getByText(text)).toBeInTheDocument();
    }
    expect(within(region).getByRole("heading", { name: "Pagos a tarjetas" })).toBeInTheDocument();
  });

  it("reconciles Σ efectivo/crédito (the split) between both views", () => {
    splitSpy.mockClear();
    const old = render(<SummaryContent {...base} summary={summary({ credit_expenses: "250000" })} />);
    const oldArgs = splitSpy.mock.calls.at(-1)?.[0];
    old.unmount();
    splitSpy.mockClear();
    render(<SummaryContentV2 {...base} summary={summary({ credit_expenses: "250000" })} />);
    // The split is inside "Más detalles": open it, then compare what it received.
    return userEvent.click(screen.getByRole("button", { name: "Más detalles" })).then(() => {
      expect(splitSpy.mock.calls.at(-1)?.[0]).toEqual(oldArgs);
    });
  });
});
