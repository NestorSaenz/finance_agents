import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatMoney } from "@/lib/format";
import type { GoalPlanStatus, GoalPlanStatusList } from "@/lib/types";

import { GoalPlanProgress } from "./GoalPlanProgress";

function status(over: Partial<GoalPlanStatus> = {}): GoalPlanStatus {
  return {
    goal_id: "g1",
    goal_name: "Viaje a Japón",
    currency: "COP",
    month: "2026-10",
    planned: "500000",
    effective_planned: "500000",
    contributed_gross: "320000",
    withdrawn: "0",
    remaining: "180000",
    percentage: 64,
    is_met: false,
    goal_completed: false,
    ...over,
  };
}

function data(statuses: GoalPlanStatus[], over: Partial<GoalPlanStatusList> = {}): GoalPlanStatusList {
  return {
    statuses,
    total_planned: { COP: "500000" },
    total_effective_planned: { COP: "500000" },
    total_saved: { COP: "320000" },
    total_withdrawn: { COP: "0" },
    ...over,
  };
}

/** formatMoney uses a no-break space; testing-library normalises it away. */
const text = (value: string) => (content: string) =>
  content.replace(/\s/g, " ") === value.replace(/\s/g, " ");

describe("GoalPlanProgress", () => {
  it("renders nothing without plans", () => {
    const { container, rerender } = render(<GoalPlanProgress data={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<GoalPlanProgress data={data([], { total_effective_planned: {} })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows aportado de planeado, 'faltan' and a brand (not green, not red) bar below 100%", () => {
    render(<GoalPlanProgress data={data([status()])} />);
    expect(screen.getByText("Ahorro planificado · no es gasto")).toBeInTheDocument();
    expect(screen.getByText(/aportado/, { selector: "span" }).textContent).toContain(
      `aportado ${formatMoney(320000)} de ${formatMoney(500000)}`,
    );
    expect(screen.getByText(text(`faltan ${formatMoney(180000)}`))).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: "Plan de Viaje a Japón" });
    expect(bar).toHaveAttribute("aria-valuenow", "64");
    expect(bar.firstElementChild?.className).toContain("bg-brand-600");
    expect(bar.getAttribute("aria-valuetext")).toBe(
      `aportado ${formatMoney(320000)} de ${formatMoney(500000)}`,
    );
  });

  it("turns green with '✓ cumplido' at 100% and never uses a red class", () => {
    const { container } = render(
      <GoalPlanProgress
        data={data([
          status({ contributed_gross: "700000", remaining: "0", percentage: 140, is_met: true }),
        ])}
      />,
    );
    expect(screen.getByText("✓ cumplido")).toBeInTheDocument();
    expect(screen.queryByText(/faltan/)).toBeNull();
    const bar = screen.getByRole("progressbar");
    expect(bar.firstElementChild?.className).toContain("bg-positive");
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    expect(container.innerHTML).not.toMatch(/negative|red-|rose-/);
  });

  it("notes withdrawals and a completed goal", () => {
    render(
      <GoalPlanProgress
        data={data([status({ withdrawn: "100000", goal_completed: true })])}
      />,
    );
    expect(screen.getByText(text(`retiraste ${formatMoney(100000)}`))).toBeInTheDocument();
    expect(screen.getByText("meta completada")).toBeInTheDocument();
  });

  it("totals per currency without mixing them", () => {
    render(
      <GoalPlanProgress
        data={data(
          [
            status(),
            status({ goal_id: "g2", goal_name: "Laptop", currency: "USD", planned: "100", effective_planned: "100", contributed_gross: "40", remaining: "60" }),
          ],
          {
            total_effective_planned: { COP: "500000", USD: "100" },
            total_saved: { COP: "320000", USD: "40" },
          },
        )}
      />,
    );
    const totals = screen.getAllByText(/^Planeado/);
    expect(totals).toHaveLength(2);
    expect(totals[0].textContent).toContain(formatMoney(500000, "COP"));
    expect(totals[1].textContent).toContain(formatMoney(100, "USD"));
    expect(totals[0].textContent).not.toContain(formatMoney(100, "USD"));
  });
});
