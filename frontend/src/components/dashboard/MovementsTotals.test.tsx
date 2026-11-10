import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatMoney } from "@/lib/format";
import type { MovementTotals } from "@/lib/movements";

import { MovementsTotals } from "./MovementsTotals";

const totals = (over: Partial<MovementTotals> = {}): MovementTotals => ({
  expenses: 0,
  paid: 0,
  saved: 0,
  withdrawn: 0,
  savedSpent: 0,
  ...over,
});

describe("MovementsTotals", () => {
  it("cash: headline = expenses + paid + saved, with only non-zero parts", () => {
    render(
      <MovementsTotals
        mode="cash"
        count={5}
        totals={totals({ expenses: 1000, paid: 2000, saved: 500, withdrawn: 300 })}
      />,
    );
    expect(screen.getByText(/movimiento\(s\)/).textContent).toContain(
      `salió de tu caja ${formatMoney(3500)}`,
    );
    const line = screen.getByText(/^Gastos en efectivo/, { selector: "p" });
    expect(line.textContent).toMatch(/Pagos a tarjetas/);
    expect(line.textContent).toMatch(/Apartado para metas/);
    expect(screen.getByText(/Volvió de tus metas/).textContent).toContain(`+${formatMoney(300)}`);
  });

  it("cash: omits zero parts and their notes", () => {
    render(
      <MovementsTotals mode="cash" count={2} totals={totals({ expenses: 1000, saved: 500 })} />,
    );
    const line = screen.getByText(/^Gastos en efectivo/, { selector: "p" });
    expect(line.textContent).not.toMatch(/Pagos a tarjetas/);
    expect(screen.queryByText(/Volvió de tus metas/)).toBeNull();
    expect(screen.queryByText(/por eso no se suman/)).toBeNull();
    expect(screen.getByText(/ahorro: sigue siendo tuyo/)).toBeInTheDocument();
  });

  it("all: gastado = consumo + counted aportes, with the breakdown and the note", () => {
    render(
      <MovementsTotals
        mode="all"
        count={3}
        totals={totals({ expenses: 1000, saved: 700, savedSpent: 500 })}
      />,
    );
    expect(screen.getByText(/movimiento\(s\)/).textContent).toContain(
      `gastado ${formatMoney(1500)}`,
    );
    const breakdown = screen.getByText(/^consumo/, { selector: "p" });
    expect(breakdown.textContent).toContain(formatMoney(1000));
    expect(breakdown.textContent).toContain(`apartado a metas ${formatMoney(500)}`);
    expect(screen.getByText(/Incluye lo apartado a metas/)).toBeInTheDocument();
    expect(screen.queryByText(/Además apartaste/)).toBeNull();
  });

  it("all: without counted aportes (before the cutoff) keeps the old text and value", () => {
    render(
      <MovementsTotals mode="all" count={3} totals={totals({ expenses: 1000, saved: 500 })} />,
    );
    expect(screen.getByText(/movimiento\(s\)/).textContent).toContain(
      `gastado ${formatMoney(1000)}`,
    );
    expect(screen.queryByText(/^consumo/, { selector: "p" })).toBeNull();
    expect(screen.getByText(/No incluye pagos a tarjetas ni movimientos de metas/)).toBeInTheDocument();
  });

  it("card: only the gastado header", () => {
    render(
      <MovementsTotals
        mode="card"
        count={1}
        totals={totals({ expenses: 1000, saved: 500, savedSpent: 500 })}
      />,
    );
    expect(screen.getByText(/movimiento\(s\)/).textContent).toContain(
      `gastado ${formatMoney(1000)}`,
    );
    expect(screen.queryByText(/^consumo/, { selector: "p" })).toBeNull();
    expect(screen.queryByText(/Igual a «Gastos»/)).toBeNull();
  });

  it("cash with only saved > 0 still shows the 'Apartado para metas' breakdown", () => {
    render(<MovementsTotals mode="cash" count={1} totals={totals({ saved: 500 })} />);
    expect(screen.getByText(/movimiento\(s\)/).textContent).toContain(
      `salió de tu caja ${formatMoney(500)}`,
    );
    expect(
      screen.getByText(/^Apartado para metas/, { selector: "p" }).textContent,
    ).toContain(formatMoney(500));
  });

  it("cash hides the breakdown when the single part is cash or payments", () => {
    const { rerender } = render(
      <MovementsTotals mode="cash" count={1} totals={totals({ expenses: 500 })} />,
    );
    expect(screen.queryByText(/^Gastos en efectivo/, { selector: "p" })).toBeNull();
    rerender(<MovementsTotals mode="cash" count={1} totals={totals({ paid: 500 })} />);
    expect(screen.queryByText(/^Pagos a tarjetas/, { selector: "p" })).toBeNull();
  });

  it("the withdrawn amount uses ink with a plus sign, not the low-contrast positive tone", () => {
    render(<MovementsTotals mode="cash" count={1} totals={totals({ expenses: 10, withdrawn: 5 })} />);
    const amount = screen.getByText(/Volvió de tus metas/).querySelector("span");
    expect(amount?.className).toContain("text-ink");
    expect(amount?.className).not.toContain("text-positive");
  });
});
