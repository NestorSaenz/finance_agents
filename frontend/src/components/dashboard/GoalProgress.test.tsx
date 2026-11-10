import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Goal } from "@/lib/types";

import { GoalProgress } from "./GoalProgress";

function goal(over: Partial<Goal> = {}): Goal {
  return {
    id: "g1",
    name: "Viaje",
    target_amount: "1000",
    current_amount: "250",
    status: "active",
    ...over,
  };
}

const fillOf = (container: HTMLElement): string =>
  (container.querySelector(".bg-brand-600, .bg-positive") as HTMLElement).style.width;

describe("GoalProgress", () => {
  it("fills proportionally and caps at 100%", () => {
    const { container, rerender } = render(<GoalProgress goals={[goal()]} />);
    expect(fillOf(container)).toBe("25%");
    rerender(<GoalProgress goals={[goal({ current_amount: "5000" })]} />);
    expect(fillOf(container)).toBe("100%");
  });

  it("never renders a negative width for a negative balance", () => {
    const { container } = render(<GoalProgress goals={[goal({ current_amount: "-300" })]} />);
    expect(fillOf(container)).toBe("0%");
  });
});
