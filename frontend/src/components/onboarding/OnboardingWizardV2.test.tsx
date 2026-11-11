import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingWizard } from "./OnboardingWizard";

const { onboardingMock, budgetMock } = vi.hoisted(() => ({
  onboardingMock: vi.fn(),
  budgetMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    completeOnboarding: (...args: unknown[]) => onboardingMock(...args),
    createBudget: (...args: unknown[]) => budgetMock(...args),
    createCard: vi.fn().mockResolvedValue({}),
    createRecurring: vi.fn().mockResolvedValue({}),
  },
}));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ token: "tok" }),
}));

beforeEach(() => {
  onboardingMock.mockReset().mockResolvedValue({});
  budgetMock.mockReset().mockResolvedValue({});
  window.localStorage.clear();
});
afterEach(() => window.history.replaceState(null, "", "/"));

async function toCapsStep(income = "14350000") {
  await userEvent.type(screen.getByLabelText(/Ingreso mensual/i), income);
  await userEvent.click(screen.getByText("Continuar"));
}

describe("OnboardingWizard with ?nuevo=1 (redesigned caps step)", () => {
  it("shows the new step: formatted amount, summary and a payload of plain numbers", async () => {
    window.history.replaceState(null, "", "/?nuevo=1");
    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);
    await toCapsStep();

    await userEvent.click(screen.getByRole("button", { name: /Alimentación/ }));
    const input = screen.getByLabelText("Tope mensual para Alimentación");
    await userEvent.type(input, "1500000");
    expect(input).toHaveValue("1.500.000");
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuetext",
      "10,5% de tu ingreso",
    );

    await userEvent.click(screen.getByText("Continuar")); // -> cards
    await userEvent.click(screen.getByText("Continuar")); // -> recurring
    await userEvent.click(screen.getByText("Finalizar"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(budgetMock).toHaveBeenCalledTimes(1);
    expect(budgetMock.mock.calls[0]?.[0]).toMatchObject({
      category: "alimentacion",
      amount: 1500000,
    });
  });

  it("a created category is sent normalized and removing one drops it from the payload", async () => {
    window.history.replaceState(null, "", "/?nuevo=1");
    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);
    await toCapsStep();

    await userEvent.type(
      screen.getByLabelText("Busca o escribe una categoría nueva"),
      "  Jardinería  {Enter}",
    );
    await userEvent.type(screen.getByLabelText("Tope mensual para Jardinería"), "300000");
    await userEvent.click(screen.getByRole("button", { name: /Salud/ }));
    await userEvent.type(screen.getByLabelText("Tope mensual para Salud"), "100000");
    await userEvent.click(screen.getByRole("button", { name: "Quitar Salud" }));

    await userEvent.click(screen.getByText("Continuar"));
    await userEvent.click(screen.getByText("Continuar"));
    await userEvent.click(screen.getByText("Finalizar"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(budgetMock).toHaveBeenCalledTimes(1);
    expect(budgetMock.mock.calls[0]?.[0]).toMatchObject({
      category: "jardinería",
      amount: 300000,
    });
  });

  it("the card becomes a bounded column (summary / scroll / footer) only on the new step 2", async () => {
    window.history.replaceState(null, "", "/?nuevo=1");
    render(<OnboardingWizard onDone={() => {}} />);
    const card = () => screen.getByText(/Paso \d de 4/).closest("div[class*='rounded-2xl']") as HTMLElement;
    expect(card().className).not.toContain("flex-col"); // step 1 untouched
    await userEvent.click(screen.getByText("Continuar"));
    expect(card().className).toContain("flex-col");
    expect(card().className).toContain("max-h-[calc(100dvh-2rem)]");
    expect(card().className).toContain("overflow-hidden");
  });

  it("without income the summary has no percentage", async () => {
    window.history.replaceState(null, "", "/?nuevo=1");
    render(<OnboardingWizard onDone={() => {}} />);
    await userEvent.click(screen.getByText("Continuar"));
    await userEvent.click(screen.getByRole("button", { name: /Alimentación/ }));
    await userEvent.type(screen.getByLabelText("Tope mensual para Alimentación"), "1500000");
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.queryByText(/de tu ingreso/)).toBeNull();
  });

  it("the choice persists: the next visit without the param keeps the new step", async () => {
    window.history.replaceState(null, "", "/?nuevo=1");
    const first = render(<OnboardingWizard onDone={() => {}} />);
    first.unmount();
    window.history.replaceState(null, "", "/");
    render(<OnboardingWizard onDone={() => {}} />);
    await userEvent.click(screen.getByText("Continuar"));
    expect(screen.getByRole("textbox", { name: "Busca o escribe una categoría nueva" })).toBeInTheDocument();
  });
});

describe("OnboardingWizard with the switch off (default)", () => {
  it("keeps today's step: number input, 'Ver más', no summary", async () => {
    render(<OnboardingWizard onDone={() => {}} />);
    await toCapsStep("30000");

    expect(screen.getByText("Ver más")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Alimentación" }));
    const input = screen.getByLabelText(/Tope mensual para Alimentación/i);
    expect(input).toHaveAttribute("type", "number");
    expect(screen.queryByRole("progressbar")).toBeNull();
    const card = screen.getByText(/Paso 2 de 4/).closest("div[class*='rounded-2xl']") as HTMLElement;
    expect(card.className).not.toContain("flex-col");
    expect(card.className).not.toContain("overflow-hidden");
  });

  it("?nuevo=0 turns a stored switch off", async () => {
    window.localStorage.setItem("safi:newDesign", "1");
    window.history.replaceState(null, "", "/?nuevo=0");
    render(<OnboardingWizard onDone={() => {}} />);
    await userEvent.click(screen.getByText("Continuar"));
    expect(screen.getByText("Ver más")).toBeInTheDocument();
  });
});
