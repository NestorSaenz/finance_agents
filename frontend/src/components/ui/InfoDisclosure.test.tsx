import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { InfoDisclosure } from "./InfoDisclosure";

function setup() {
  render(
    <div className="flex flex-wrap">
      <InfoDisclosure label="Balance">Los cargos a crédito cuentan completos.</InfoDisclosure>
    </div>,
  );
  return screen.getByRole("button", { name: "Qué significa Balance" });
}

describe("InfoDisclosure", () => {
  it("is a named 44x44 button, closed by default, wired with aria-expanded/controls", () => {
    const button = setup();
    expect(button).toHaveAttribute("aria-expanded", "false");
    const controls = button.getAttribute("aria-controls");
    expect(controls).toBeTruthy();
    expect(button.className).toContain("h-11");
    expect(button.className).toContain("w-11");
    expect(button.className).toContain("focus-visible:ring-2");
    expect(screen.queryByText("Los cargos a crédito cuentan completos.")).toBeNull();
  });

  it("opens and closes with the mouse, showing the note BELOW the button (not a tooltip)", async () => {
    const button = setup();
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const note = screen.getByText("Los cargos a crédito cuentan completos.");
    expect(note.id).toBe(button.getAttribute("aria-controls"));
    expect(button.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(note.closest("[role='tooltip']")).toBeNull();
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Los cargos a crédito cuentan completos.")).toBeNull();
  });

  it("works with the keyboard: Enter and Space toggle it", async () => {
    const button = setup();
    await userEvent.tab();
    expect(button).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");
    await userEvent.keyboard(" ");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});
