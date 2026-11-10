import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { GoalMonthLine } from "@/lib/types";

import { GoalPlanHistory } from "./GoalPlanHistory";

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
  line({ month: "2026-09", saved: "500000" }),
  line({ goal_id: "g2", month: "2026-09", planned: "300000", saved: "100000" }),
  line({ month: "2026-10", saved: "200000" }),
  line({ month: "2026-08", planned: null }),
];

function renderHistory(over: Partial<React.ComponentProps<typeof GoalPlanHistory>> = {}) {
  const onSelectMonth = vi.fn();
  render(
    <GoalPlanHistory
      lines={LINES}
      currency="COP"
      selectedMonth="2026-10"
      endMonth="2026-10"
      onSelectMonth={onSelectMonth}
      {...over}
    />,
  );
  return onSelectMonth;
}

const toggle = () => screen.getByRole("button", { name: /Historial de planes/ });

describe("GoalPlanHistory", () => {
  it("renders nothing when no month has a plan", () => {
    const { container } = render(
      <GoalPlanHistory
        lines={[line({ planned: null })]}
        currency="COP"
        selectedMonth={null}
        endMonth="2026-10"
        onSelectMonth={() => {}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("is closed by default and toggles with aria-expanded", async () => {
    renderHistory();
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
    expect(toggle().textContent).toContain("últimos 5 meses");
    expect(screen.queryByRole("list")).toBeNull();

    await userEvent.click(toggle());
    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Toca un mes para verlo")).toBeInTheDocument();
    // Months without plan (Ago) are not listed.
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("summarises each month with its met/total goals", async () => {
    renderHistory();
    await userEvent.click(toggle());
    const sep = screen.getByRole("button", { name: /Sep 2026/ });
    expect(sep.textContent).toContain("1/2 cumplidas");
    expect(screen.getByRole("button", { name: /Oct 2026/ }).textContent).toContain("0/1 cumplidas");
  });

  it("tapping a month calls onSelectMonth with YYYY-MM", async () => {
    const onSelectMonth = renderHistory();
    await userEvent.click(toggle());
    await userEvent.click(screen.getByRole("button", { name: /Sep 2026/ }));
    expect(onSelectMonth).toHaveBeenCalledWith("2026-09");
  });

  it("marks the viewed month with aria-current, and none with 'Todo'", async () => {
    const { unmount } = render(
      <GoalPlanHistory
        lines={LINES}
        currency="COP"
        selectedMonth="2026-10"
        endMonth="2026-10"
        onSelectMonth={() => {}}
      />,
    );
    await userEvent.click(toggle());
    expect(screen.getByRole("button", { name: /Oct 2026/ })).toHaveAttribute("aria-current", "date");
    expect(screen.getByRole("button", { name: /Sep 2026/ })).not.toHaveAttribute("aria-current");
    unmount();

    render(
      <GoalPlanHistory
        lines={LINES}
        currency="COP"
        selectedMonth={null}
        endMonth="2026-10"
        onSelectMonth={() => {}}
      />,
    );
    await userEvent.click(toggle());
    expect(
      screen.getAllByRole("button").filter((b) => b.hasAttribute("aria-current")),
    ).toHaveLength(0);
  });
});
