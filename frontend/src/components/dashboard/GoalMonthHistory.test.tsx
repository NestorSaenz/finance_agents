import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { formatMoney } from "@/lib/format";
import type { GoalMonthLine } from "@/lib/types";

import { GoalMonthHistory } from "./GoalMonthHistory";

function line(over: Partial<GoalMonthLine> = {}): GoalMonthLine {
  return {
    goal_id: "g1",
    goal_name: "Viaje",
    currency: "COP",
    month: "2026-10",
    planned: "500000",
    saved: "0",
    withdrawn: "0",
    cumulative: "0",
    ...over,
  };
}

const LINES = [
  line({ month: "2026-09", saved: "500000", planned: "500000" }),
  line({ month: "2026-10", saved: "320000", withdrawn: "50000" }),
  line({ month: "2026-08", planned: null, saved: "0" }),
];

describe("GoalMonthHistory", () => {
  it("renders nothing without lines", () => {
    const { container } = render(<GoalMonthHistory goalName="Viaje" lines={[]} selectedMonth="2026-10" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("expands and collapses with aria-expanded", async () => {
    render(<GoalMonthHistory goalName="Viaje" lines={LINES} selectedMonth="2026-10" />);
    const toggle = screen.getByRole("button", { name: /Ver mes a mes/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list")).toBeNull();

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("listitem")).toHaveLength(3);

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("shows saved / planned, the chip per month, the withdrawal note and 'sin plan'", async () => {
    render(<GoalMonthHistory goalName="Viaje" lines={LINES} selectedMonth="2026-10" />);
    await userEvent.click(screen.getByRole("button", { name: /Ver mes a mes/ }));

    const items = screen.getAllByRole("listitem");
    const sep = items.find((li) => li.textContent?.includes("Sep 2026"));
    const oct = items.find((li) => li.textContent?.includes("Oct 2026"));
    const ago = items.find((li) => li.textContent?.includes("Ago 2026"));
    expect(sep?.textContent).toContain(`${formatMoney(500000)} / ${formatMoney(500000)}`);
    expect(sep?.textContent).toContain("✓");
    expect(oct?.textContent).toContain(`faltan ${formatMoney(180000)}`);
    expect(oct?.textContent).toContain(`retiraste ${formatMoney(50000)}`);
    expect(ago?.textContent).toContain("sin plan");
  });

  it("highlights only the chosen month", async () => {
    render(<GoalMonthHistory goalName="Viaje" lines={LINES} selectedMonth="2026-10" />);
    await userEvent.click(screen.getByRole("button", { name: /Ver mes a mes/ }));
    const current = screen
      .getAllByRole("listitem")
      .filter((li) => li.getAttribute("aria-current") === "date");
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toContain("Oct 2026");
  });

  it("names the goal in the toggle's accessible name and has a 44px touch target", () => {
    render(<GoalMonthHistory goalName="Viaje a Japón" lines={LINES} selectedMonth="2026-10" />);
    const toggle = screen.getByRole("button", { name: "Ver mes a mes de Viaje a Japón" });
    expect(toggle.className).toContain("min-h-[44px]");
  });

  it("treats a plan of 0 as 'sin plan', not as cumplido", async () => {
    render(
      <GoalMonthHistory
        goalName="Viaje"
        lines={[line({ month: "2026-10", planned: "0", saved: "0" })]}
        selectedMonth="2026-10"
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Ver mes a mes/ }));
    const item = screen.getByRole("listitem");
    expect(item.textContent).toContain("sin plan");
    expect(item.textContent).not.toContain("✓");
  });

  it("uses effective_planned for 'faltan' when the backend sends it", async () => {
    render(
      <GoalMonthHistory
        goalName="Viaje"
        lines={[line({ planned: "500000", effective_planned: "400000", saved: "300000" })]}
        selectedMonth="2026-10"
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Ver mes a mes/ }));
    expect(screen.getByRole("listitem").textContent).toContain(`faltan ${formatMoney(100000)}`);
  });
});
