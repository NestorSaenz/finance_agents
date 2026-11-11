import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { formatMoney } from "@/lib/format";

import { CategoryCapsStepV2 } from "./CategoryCapsStepV2";

const COMMON = ["alimentacion", "transporte", "restaurantes", "salud", "vivienda", "servicios"];
const MORE = ["educacion", "ropa", "viajes"];

/** Stateful host mirroring what the wizard does with the callbacks. */
function Harness({
  income = 14350000,
  initialSelected = [] as string[],
  initialCaps = {} as Record<string, string>,
  onContinue = () => {},
  onAddCustomSpy = () => {},
}: {
  income?: number | null;
  initialSelected?: string[];
  initialCaps?: Record<string, string>;
  onContinue?: () => void;
  onAddCustomSpy?: (c: string) => void;
}) {
  const [selected, setSelected] = useState(initialSelected);
  const [caps, setCaps] = useState(initialCaps);
  const [custom, setCustom] = useState<string[]>([]);
  return (
    <CategoryCapsStepV2
      commonCategories={COMMON}
      moreCategories={MORE}
      customCategories={custom}
      selected={selected}
      caps={caps}
      income={income}
      currency="COP"
      submitting={false}
      onToggle={(c) =>
        setSelected((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
      }
      onAddCustom={(c) => {
        onAddCustomSpy(c);
        setCustom((prev) => (prev.includes(c) ? prev : [...prev, c]));
        setSelected((prev) => (prev.includes(c) ? prev : [...prev, c]));
      }}
      onCapChange={(c, v) => setCaps((prev) => ({ ...prev, [c]: v }))}
      onBack={() => {}}
      onContinue={onContinue}
    />
  );
}

const field = (name: RegExp | string) => screen.getByRole("textbox", { name });
/** The visible summary line (not the screen-reader live region). */
const visibleSummary = (pattern: RegExp) =>
  screen.getAllByText(pattern, { selector: "p" }).find((p) => !p.hasAttribute("aria-live")) as HTMLElement;
const chip = (name: string) => screen.getByRole("button", { name: new RegExp(name) });

describe("CategoryCapsStepV2", () => {
  it("formats the amount with thousands as you type and exposes a numeric keypad", async () => {
    render(<Harness initialSelected={["alimentacion"]} />);
    const input = field("Tope mensual para Alimentación");
    expect(input).toHaveAttribute("inputmode", "numeric");
    expect(input).toHaveAttribute("type", "text");

    await userEvent.type(input, "1500000");
    expect(input).toHaveValue("1.500.000");
  });

  it("a pasted amount keeps only the digits", async () => {
    render(<Harness initialSelected={["alimentacion"]} />);
    const input = field("Tope mensual para Alimentación");
    await userEvent.click(input);
    await userEvent.paste("$1.500.000");
    expect(input).toHaveValue("1.500.000");
  });

  it("shows the count, the total and the share of income; announces once typing pauses", async () => {
    render(<Harness initialSelected={["alimentacion", "vivienda"]} />);
    await userEvent.type(field("Tope mensual para Alimentación"), "1500000");
    await userEvent.type(field("Tope mensual para Vivienda"), "2000000");

    const visible = visibleSummary(/2 topes/);
    expect(visible.textContent).toContain("24,4% de tu ingreso");
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuetext", "24,4% de tu ingreso");
    expect(bar).toHaveAttribute("aria-valuenow", "24");
    // Per-row share: short on screen, full sentence for screen readers.
    expect(screen.getByText("10,5% de tu ingreso")).toHaveClass("sr-only");
    expect(screen.getByText("13,9% de tu ingreso")).toHaveClass("sr-only");

    // The live region is not the visible text and settles after a pause.
    const live = document.querySelector("[aria-live='polite']");
    expect(visible.closest("[aria-live]")).toBeNull();
    await waitFor(() => expect(live?.textContent).toContain("24,4% de tu ingreso"), { timeout: 2000 });
    expect(live?.textContent).toContain("2 topes");
  });

  it("does not re-announce on every key: the live text lags behind the visible one", () => {
    vi.useFakeTimers();
    try {
      render(<Harness initialSelected={["alimentacion"]} />);
      const live = document.querySelector("[aria-live='polite']");
      expect(live?.textContent).toContain("1 tope, 0");
      const input = field("Tope mensual para Alimentación");
      act(() => {
        input.focus();
      });
      // Simulate typing quickly with direct events.
      for (const digit of ["1", "15", "150"]) {
        act(() => {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
          setter?.call(input, digit);
          input.dispatchEvent(new Event("input", { bubbles: true }));
        });
      }
      expect(visibleSummary(/1 tope/).textContent).toContain("150");
      expect(live?.textContent).toContain("1 tope, 0"); // not announced yet
      act(() => {
        vi.advanceTimersByTime(800);
      });
      expect(live?.textContent).toContain("150");
    } finally {
      vi.useRealTimers();
    }
  });

  it("without income there is no percentage and no bar", async () => {
    render(<Harness income={null} initialSelected={["alimentacion"]} />);
    await userEvent.type(field("Tope mensual para Alimentación"), "1500000");
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.queryByText(/de tu ingreso/)).toBeNull();
    expect(screen.getAllByText(/1 tope/).length).toBeGreaterThan(0);
  });

  it("over 100% clamps the bar and says so in words, not just color", async () => {
    render(<Harness income={1000000} initialSelected={["alimentacion"]} />);
    await userEvent.type(field("Tope mensual para Alimentación"), "1500000");
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    expect(bar.getAttribute("aria-valuetext")).toContain("superas tu ingreso");
    expect(screen.getByText(/Superas tu ingreso/)).toBeInTheDocument();
  });

  it("removes a category from the list and it returns to the chips", async () => {
    render(<Harness initialSelected={["alimentacion"]} />);
    expect(screen.queryByRole("button", { name: "Alimentación" })).toBeNull(); // not a chip
    await userEvent.click(screen.getByRole("button", { name: "Quitar Alimentación" }));
    expect(screen.queryByRole("textbox", { name: /Tope mensual para Alimentación/ })).toBeNull();
    expect(chip("Alimentación")).toBeInTheDocument();
  });

  it("chips offer only what is still missing; choosing one moves it to the list and focuses its amount", async () => {
    render(<Harness initialSelected={["alimentacion"]} />);
    expect(screen.queryByRole("button", { name: "Alimentación" })).toBeNull();
    await userEvent.click(chip("Transporte"));
    const input = field("Tope mensual para Transporte");
    expect(input).toBeInTheDocument();
    // The chip they pressed is gone: focus lands on the new row, not on <body>.
    expect(input).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Transporte" })).toBeNull();
  });

  it("creating a category also moves focus to its amount", async () => {
    render(<Harness />);
    await userEvent.type(screen.getByLabelText("Busca o escribe una categoría nueva"), "colegio{Enter}");
    expect(field("Tope mensual para Colegio")).toHaveFocus();
  });

  it("no input ever grabs focus on its own (no autoFocus)", async () => {
    render(<Harness initialSelected={["alimentacion", "vivienda"]} />);
    for (const textbox of screen.getAllByRole("textbox")) {
      expect(textbox).not.toHaveFocus();
    }
  });

  it("'Más categorías' is a real toggle (aria-expanded) that reveals and hides the less common ones", async () => {
    render(<Harness />);
    expect(screen.queryByRole("button", { name: "Educación" })).toBeNull();
    const more = screen.getByRole("button", { name: /Más categorías/ });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(more);
    expect(chip("Educación")).toBeInTheDocument();
    const less = screen.getByRole("button", { name: /Menos categorías/ });
    expect(less).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(less);
    expect(screen.queryByRole("button", { name: "Educación" })).toBeNull();
  });

  it("search is accent- and case-insensitive and filters the chips", async () => {
    render(<Harness />);
    await userEvent.type(screen.getByLabelText("Busca o escribe una categoría nueva"), "EDUCACION");
    expect(chip("Educación")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Transporte/ })).toBeNull();
    // An existing category (even if folded under "Más") is not offered for creation.
    expect(screen.queryByRole("button", { name: /Crear/ })).toBeNull();
  });

  it("offers 'Crear «x»' for a new name; click or Enter creates it as 'tuya'", async () => {
    render(<Harness />);
    const search = screen.getByLabelText("Busca o escribe una categoría nueva");
    await userEvent.type(search, "Jardinería");
    expect(screen.getByRole("button", { name: /Crear «jardinería»/ })).toBeInTheDocument();
    await userEvent.type(search, "{Enter}");
    expect(field("Tope mensual para Jardinería")).toBeInTheDocument();
    expect(screen.getByText("tuya")).toBeInTheDocument();
    expect(search).toHaveValue("");

    // The same name without the accent matches the one just created: no second create.
    await userEvent.type(search, "jardineria");
    expect(screen.queryByRole("button", { name: /Crear/ })).toBeNull();
  });

  it("Enter on an existing match chooses it", async () => {
    render(<Harness />);
    const search = screen.getByLabelText("Busca o escribe una categoría nueva");
    await userEvent.type(search, "salud{Enter}");
    expect(field("Tope mensual para Salud")).toBeInTheDocument();
  });

  it("shows the first 5 topes and 'Ver los N topes' expands with aria-expanded", async () => {
    const selected = ["alimentacion", "transporte", "restaurantes", "salud", "vivienda", "servicios"];
    render(<Harness initialSelected={selected} />);
    expect(screen.getAllByRole("textbox", { name: /Tope mensual para/ })).toHaveLength(5);
    const toggle = screen.getByRole("button", { name: /Ver los 6 topes/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle.className).toContain("min-h-11");

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("textbox", { name: /Tope mensual para/ })).toHaveLength(6);
    expect(screen.getByRole("button", { name: /Ver menos/ })).toBeInTheDocument();
  });

  it("with 5 or fewer there is no 'Ver los' toggle", () => {
    render(<Harness initialSelected={["alimentacion", "transporte"]} />);
    expect(screen.queryByRole("button", { name: /Ver los/ })).toBeNull();
  });

  it("the footer has 48px buttons, respects the safe area and is not sticky or fixed", async () => {
    const onContinue = vi.fn();
    render(<Harness onContinue={onContinue} />);
    const next = screen.getByRole("button", { name: "Continuar" });
    expect(next.className).toContain("min-h-12");
    expect(screen.getByRole("button", { name: "Atrás" }).className).toContain("min-h-12");
    const footer = next.parentElement?.parentElement as HTMLElement;
    expect(footer.className).toContain("shrink-0");
    expect(footer.className).not.toMatch(/sticky|fixed/);
    expect(footer.style.paddingBottom).toContain("safe-area-inset-bottom");
    await userEvent.click(next);
    expect(onContinue).toHaveBeenCalled();
  });

  it("DOM order is summary -> scrolling content -> footer, and the footer does not repeat the totals", async () => {
    render(<Harness initialSelected={["alimentacion"]} />);
    await userEvent.type(field("Tope mensual para Alimentación"), "1500000");
    const progress = screen.getByRole("progressbar");
    const heading = screen.getByRole("heading", { name: "Topes por categoría" });
    const next = screen.getByRole("button", { name: "Continuar" });
    const scroller = heading.closest(".overflow-y-auto") as HTMLElement;
    expect(scroller).not.toBeNull();
    // Only the middle region scrolls.
    expect(progress.closest(".overflow-y-auto")).toBeNull();
    expect(next.closest(".overflow-y-auto")).toBeNull();
    const order = (a: Node, b: Node) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING;
    expect(order(progress, scroller)).toBeTruthy();
    expect(order(scroller, next)).toBeTruthy();
    // The count/total live in the summary only.
    const footer = next.parentElement?.parentElement as HTMLElement;
    expect(footer.textContent).not.toMatch(/tope\b|topes|\$|%/);
  });

  it("the visible share is short ('10,5%'), not three lines; names are not truncated", async () => {
    render(<Harness initialSelected={["alimentacion"]} />);
    await userEvent.type(field("Tope mensual para Alimentación"), "1500000");
    const row = screen.getByText("Alimentación").parentElement as HTMLElement;
    expect(row.textContent).toContain("10,5%");
    expect(within(row).getByText("10,5%", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Alimentación").className).not.toContain("truncate");
    expect(field("Tope mensual para Alimentación").className).toContain("w-28");
    expect(field("Tope mensual para Alimentación")).toHaveAccessibleDescription("10,5% de tu ingreso");
  });

  it("is keyboard operable: Tab reaches the search, Enter/Space activate chips", async () => {
    render(<Harness />);
    await userEvent.tab();
    expect(screen.getByLabelText("Busca o escribe una categoría nueva")).toHaveFocus();
    await userEvent.tab();
    const first = within(document.body).getByRole("button", { name: /Alimentación/ });
    expect(first).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(field("Tope mensual para Alimentación")).toBeInTheDocument();
    const next = screen.getByRole("button", { name: /Transporte/ });
    next.focus();
    await userEvent.keyboard(" ");
    expect(field("Tope mensual para Transporte")).toBeInTheDocument();
  });

  it("Enter with a partial match chooses it instead of creating a junk category", async () => {
    const onAddCustom = vi.fn();
    render(<Harness onAddCustomSpy={onAddCustom} />);
    await userEvent.type(screen.getByLabelText("Busca o escribe una categoría nueva"), "rest{Enter}");
    expect(field("Tope mensual para Restaurantes")).toBeInTheDocument();
    expect(onAddCustom).not.toHaveBeenCalled();
    expect(screen.queryByText("tuya")).toBeNull();
  });

  it("'jardin' + Enter picks the existing 'Jardinería' (created before) rather than a new one", async () => {
    render(<Harness />);
    const search = screen.getByLabelText("Busca o escribe una categoría nueva");
    await userEvent.type(search, "jardinería{Enter}");
    await userEvent.click(screen.getByRole("button", { name: "Quitar Jardinería" }));
    await userEvent.type(search, "jardin{Enter}");
    expect(screen.getAllByRole("textbox", { name: /Tope mensual para Jardinería/ })).toHaveLength(1);
    expect(screen.queryByRole("textbox", { name: /Tope mensual para Jardin$/ })).toBeNull();
  });

  it("with a partial match visible, 'Crear' stays available as the explicit button", async () => {
    render(<Harness />);
    await userEvent.type(screen.getByLabelText("Busca o escribe una categoría nueva"), "rest");
    expect(chip("Restaurantes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Crear «rest»/ })).toBeInTheDocument();
  });

  it("amounts are limited to 10 digits, typing or pasting", async () => {
    render(<Harness initialSelected={["alimentacion"]} />);
    const input = field("Tope mensual para Alimentación");
    await userEvent.type(input, "123456789012345");
    expect(input).toHaveValue("1.234.567.890");
    await userEvent.clear(input);
    await userEvent.click(input);
    await userEvent.paste("99999999999999");
    expect(input).toHaveValue("9.999.999.999");
  });

  it("Backspace right after a thousands separator removes the digit before it", async () => {
    render(<Harness initialSelected={["alimentacion"]} initialCaps={{ alimentacion: "1500" }} />);
    const input = field("Tope mensual para Alimentación") as HTMLInputElement;
    expect(input).toHaveValue("1.500");
    input.focus();
    input.setSelectionRange(2, 2); // right after the "."
    await userEvent.keyboard("{Backspace}");
    expect(input).toHaveValue("500");
  });

  it("shows only a short help line, and only while the search is empty", async () => {
    render(<Harness />);
    expect(screen.getByText("Lo que elijas pasa arriba, a «Tus topes».")).toBeInTheDocument();
    expect(screen.queryByText(/Si escribes una que no existe/)).toBeNull();
    await userEvent.type(screen.getByLabelText("Busca o escribe una categoría nueva"), "x");
    expect(screen.queryByText(/Lo que elijas pasa arriba/)).toBeNull();
  });

  it("scrolls the results into view when the query changes", async () => {
    const scrollIntoView = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      render(<Harness />);
      await userEvent.type(screen.getByLabelText("Busca o escribe una categoría nueva"), "sal");
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });
});
