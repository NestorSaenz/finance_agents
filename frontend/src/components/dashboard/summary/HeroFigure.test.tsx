import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatMoney } from "@/lib/format";
import { heroFigure, type HeroFigureData } from "@/lib/heroFigure";
import { summaryFigures } from "@/lib/summary";
import type { SpendingSummary } from "@/lib/types";

import { HeroFigure } from "./HeroFigure";

const NOW = new Date(2026, 10, 15);
const money = (v: number) => formatMoney(v);
/** formatMoney uses a no-break space; testing-library normalises it away. */
const text = (value: string) => (content: string) =>
  content.replace(/\s/g, " ") === value.replace(/\s/g, " ");

function summary(over: Partial<SpendingSummary> = {}): SpendingSummary {
  return {
    period: "este_mes",
    total_income: "10000000",
    total_expenses: "1000000",
    balance: "0",
    by_category: [],
    credit_expenses: "0",
    cash_expenses: "1000000",
    ...over,
  };
}

function hero(
  over: Partial<SpendingSummary> = {},
  period = "este_mes",
  extra: { goalSaved?: number; goalWithdrawn?: number; surplus?: number } = {},
): { data: HeroFigureData; props: React.ComponentProps<typeof HeroFigure> } {
  const figures = summaryFigures({
    summary: summary(over),
    budget: null,
    profile: null,
    goals: [],
    goalSaved: extra.goalSaved ?? 0,
    goalWithdrawn: extra.goalWithdrawn ?? 0,
    cards: null,
    payments: null,
    planStatus: null,
    goalHistory: null,
    period,
    currency: "COP",
    now: NOW,
  });
  const data = heroFigure(figures, { period, accumulatedSurplus: extra.surplus ?? 0, money, now: NOW });
  return {
    data,
    props: {
      hero: data,
      income: figures.income,
      totalSpent: figures.totalSpent,
      consumo: figures.expenses,
      spentOnGoals: figures.spentOnGoals,
      balance: figures.balance,
      goalsReturned: figures.goalsReturned,
      pending: figures.pending,
    },
  };
}

describe("HeroFigure", () => {
  it("shows the figure, a progress bar with aria-valuetext, and the three stats", () => {
    const { props } = hero();
    render(<HeroFigure {...props} />);
    expect(screen.getByText("Tu mes · noviembre")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "10");
    expect(bar).toHaveAttribute("aria-valuetext", "Consumido 10% de tu ingreso");
    expect(screen.getByText("Consumido 10% de tu ingreso")).toBeInTheDocument();
    for (const label of ["Ingresos", "Gastos", "Balance"]) {
      expect(screen.getByText(label, { selector: "p" })).toBeInTheDocument();
    }
  });

  it("over 100% says so in words and keeps the bar full", () => {
    const { props } = hero({ total_income: "1000000", total_expenses: "1500000", cash_expenses: "0" });
    render(<HeroFigure {...props} />);
    expect(screen.getByText("Gastaste más que tu ingreso")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    expect(bar.firstElementChild).toHaveStyle({ width: "100%" });
  });

  it("without income: spending as the headline, the prompt, and no bar", () => {
    const { props } = hero({ total_income: "0" }, "mes_pasado");
    render(<HeroFigure {...props} />);
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText(/Registra tus ingresos para ver tu caja/)).toBeInTheDocument();
  });

  it("'todo' leads with the accumulated surplus and has no bar", () => {
    const { props } = hero({}, "todo", { surplus: 5230000 });
    render(<HeroFigure {...props} />);
    expect(screen.getByText("De toda tu historia")).toBeInTheDocument();
    expect(screen.getByText(text(money(5230000)), { selector: "p.text-3xl" })).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("goal savings: the breakdown and 'incluye lo apartado a metas' stay visible", () => {
    const { props } = hero(
      { goal_saved: "500000", total_spent: "1500000" },
      "este_mes",
      { goalSaved: 500000 },
    );
    render(<HeroFigure {...props} />);
    expect(screen.getByText(text(`Gastos: consumo ${money(1000000)} + metas ${money(500000)}`))).toBeInTheDocument();
    expect(screen.getByText(text(`Incluye ${money(500000)} apartados a metas.`))).toBeInTheDocument();
    expect(screen.getByText(/incluye lo apartado a metas\)/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuetext")).toContain(
      "incluye lo apartado a metas",
    );
  });

  it("keeps the withdrawals and pending-plan notes visible, and the Balance definition behind an 'i'", () => {
    const { props } = hero({ goal_withdrawn: "200000" });
    render(<HeroFigure {...props} goalsReturned={200000} pending={300000} />);
    expect(screen.getByText(/Además volvieron .* de tus metas/)).toBeInTheDocument();
    expect(screen.getByText(text(`Gastos sin contar ${money(300000)} por aportar`))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Qué significa Balance" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText(/Los cargos a crédito cuentan completos/)).toBeNull();
  });

  it("the negative tone uses the negative color class", () => {
    const { props } = hero({ total_income: "1000000", total_expenses: "0", cash_expenses: "2000000" });
    render(<HeroFigure {...props} />);
    expect(screen.getByText(text(money(-1000000)), { selector: "p.text-3xl" }).className).toContain("text-negative");
  });
});

describe("HeroFigure layout", () => {
  it("amounts never wrap and the three stats stack on narrow screens", () => {
    const { props } = hero({ goal_saved: "500000", total_spent: "1500000" }, "este_mes", { goalSaved: 500000 });
    const { container } = render(<HeroFigure {...props} />);
    const gastos = screen.getByText("Gastos", { selector: "p" }).nextElementSibling as HTMLElement;
    expect(gastos.className).toContain("whitespace-nowrap");
    expect(gastos.className).toContain("tabular-nums");
    const group = gastos.parentElement?.parentElement as HTMLElement;
    expect(group.className).toContain("flex-col"); // vertical rows below 440px
    expect(group.className).toContain("min-[440px]:grid-cols-3");
    expect(container.querySelectorAll("p.whitespace-nowrap")).toHaveLength(3);
  });

  it("small green figures use emerald-700 (AA); the big one keeps text-positive", () => {
    const { props } = hero();
    render(<HeroFigure {...props} />);
    const ingresos = screen.getByText("Ingresos", { selector: "p" }).nextElementSibling as HTMLElement;
    const balance = screen.getByText("Balance", { selector: "p" }).nextElementSibling as HTMLElement;
    expect(ingresos.className).toContain("text-emerald-700");
    expect(balance.className).toContain("text-emerald-700");
    expect(screen.getByText(/Tu mes/).nextElementSibling?.className).toContain("text-positive");
  });

  it("the 'i' sits on the same row as the Balance sentence, which keeps '(incluye lo apartado a metas)'", () => {
    const { props } = hero({ goal_saved: "500000", total_spent: "1500000" }, "este_mes", { goalSaved: 500000 });
    render(<HeroFigure {...props} />);
    const info = screen.getByRole("button", { name: "Qué significa Balance" });
    const sentence = screen.getByText(/^Balance: ingresos menos gastos del mes/);
    expect(sentence.textContent).toContain("(incluye lo apartado a metas)");
    expect(info.parentElement).toBe(sentence.parentElement);
    expect(sentence.parentElement?.className).toContain("flex");
  });

  it("every note sits in ONE group at one size, after the stats", () => {
    const { props } = hero({ goal_saved: "500000", total_spent: "1500000" }, "este_mes", { goalSaved: 500000 });
    render(<HeroFigure {...props} goalsReturned={1000} pending={2000} />);
    const group = screen.getByText(/Gastos: consumo/).parentElement as HTMLElement;
    expect(group.className).toContain("text-xs");
    expect(group.className).toContain("flex-col");
    for (const pattern of [/Incluye .* apartados a metas/, /Gastos sin contar/, /Además volvieron/, /^Balance: ingresos/]) {
      expect(screen.getByText(pattern).closest("div")).not.toBeNull();
    }
    const stats = screen.getByText("Ingresos", { selector: "p" }).closest("div[class*='border-t']") as HTMLElement;
    expect(stats.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
