import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { BudgetIncomeShare } from "@/lib/budgets";

import { BudgetIncomeSummary } from "./BudgetIncomeSummary";

function share(over: Partial<BudgetIncomeShare> = {}): BudgetIncomeShare {
  return { categoryTotal: 1000000, totalPct: 50, overall: null, pctById: new Map(), ...over };
}

describe("BudgetIncomeSummary", () => {
  it("shows the total and percentage", () => {
    render(<BudgetIncomeSummary share={share()} />);
    const line = screen.getByText(/Tus topes suman/);
    expect(line.textContent).toMatch(/1[.,]000[.,]000/);
    expect(line.textContent).toContain("50%");
    expect(screen.queryByText(/más que tu ingreso base/)).toBeNull();
  });

  it("shows the overall tope apart and the over-100% note", () => {
    render(
      <BudgetIncomeSummary
        share={share({ totalPct: 120, overall: { amount: 800000, pct: 80 } })}
      />,
    );
    expect(screen.getByText(/Tope general/).textContent).toContain("80%");
    expect(screen.getByText(/más que tu ingreso base/)).toBeInTheDocument();
  });

  it("renders nothing without topes to report", () => {
    const { container } = render(<BudgetIncomeSummary share={share({ categoryTotal: 0 })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
