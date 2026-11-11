import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SectionJumps } from "./SectionJumps";

function Host({ withCards = true }: { withCards?: boolean }) {
  const sections = [
    { id: "s-flujo", label: "Flujo de caja" },
    { id: "s-topes", label: "Topes" },
    ...(withCards ? [{ id: "s-tarjetas", label: "Tarjetas" }] : []),
  ];
  return (
    <div>
      <SectionJumps sections={sections} />
      <div id="s-flujo">Flujo (sin encabezado)</div>
      <div id="s-topes">
        <h3>Cómo voy en cada categoría</h3>
      </div>
      {withCards && (
        <div id="s-tarjetas">
          <h3>Tarjetas de crédito</h3>
        </div>
      )}
    </div>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  // @ts-expect-error test cleanup of the stubbed prototype method
  delete Element.prototype.scrollIntoView;
});

describe("SectionJumps", () => {
  it("has a chip per shown section, each 44px tall, and none for a missing section", () => {
    const { unmount } = render(<Host />);
    for (const name of ["Flujo de caja", "Topes", "Tarjetas"]) {
      expect(screen.getByRole("button", { name }).className).toContain("min-h-11");
    }
    unmount();
    render(<Host withCards={false} />);
    expect(screen.queryByRole("button", { name: "Tarjetas" })).toBeNull();
  });

  it("renders nothing without sections", () => {
    const { container } = render(<SectionJumps sections={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("scrolls the section into view and moves focus to its heading", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    render(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Topes" }));
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "start", behavior: "smooth" });
    const heading = screen.getByRole("heading", { name: "Cómo voy en cada categoría" });
    expect(heading).toHaveFocus();
    expect(heading).toHaveAttribute("tabindex", "-1");
  });

  it("focuses the section itself when it has no heading", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    render(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Flujo de caja" }));
    const section = screen.getByText("Flujo (sin encabezado)");
    expect(section).toHaveFocus();
  });

  it("respects prefers-reduced-motion (no smooth scroll)", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({ matches: query.includes("reduce"), media: query }) as unknown as MediaQueryList,
    );
    render(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Tarjetas" }));
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "start", behavior: "auto" });
  });
});

describe("SectionJumps chips", () => {
  it("use compact padding, keep the 44px height and name the full section for screen readers", () => {
    render(
      <SectionJumps
        sections={[{ id: "a", label: "Flujo", fullLabel: "Flujo de caja" }]}
      />,
    );
    const chip = screen.getByRole("button", { name: "Flujo de caja" });
    expect(chip.textContent).toBe("Flujo");
    expect(chip.className).toContain("px-3");
    expect(chip.className).toContain("min-h-11");
    expect(chip.parentElement?.className).toContain("overflow-x-auto"); // only as a fallback
  });
});
