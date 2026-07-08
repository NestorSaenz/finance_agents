import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingWizard } from "./OnboardingWizard";

const { onboardingMock, budgetMock, cardMock } = vi.hoisted(() => ({
  onboardingMock: vi.fn(),
  budgetMock: vi.fn(),
  cardMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    completeOnboarding: (...args: unknown[]) => onboardingMock(...args),
    createBudget: (...args: unknown[]) => budgetMock(...args),
    createCard: (...args: unknown[]) => cardMock(...args),
  },
}));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ token: "tok" }),
}));

beforeEach(() => {
  onboardingMock.mockReset().mockResolvedValue({});
  budgetMock.mockReset().mockResolvedValue({});
  cardMock.mockReset().mockResolvedValue({});
});

describe("OnboardingWizard", () => {
  it("skips without sending income", async () => {
    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);

    await userEvent.click(screen.getByText("Omitir"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onboardingMock).toHaveBeenCalledWith(
      {
        display_name: undefined,
        monthly_income: undefined,
        savings_goal_percentage: undefined,
      },
      "tok",
    );
    expect(budgetMock).not.toHaveBeenCalled();
  });

  it("submits income and category caps on finish", async () => {
    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);

    await userEvent.type(screen.getByLabelText(/Cómo te llamas/i), "Néstor");
    await userEvent.type(screen.getByLabelText(/Ingreso mensual/i), "30000");
    await userEvent.type(screen.getByLabelText(/Meta de ahorro/i), "20");
    await userEvent.click(screen.getByText("Continuar"));

    // Pick the "Alimentación" chip, then its amount input appears.
    await userEvent.click(screen.getByRole("button", { name: "Alimentación" }));
    await userEvent.type(
      screen.getByLabelText(/Tope mensual para Alimentación/i),
      "5000",
    );
    // Step 2 -> step 3 (cards), then add a card and finish.
    await userEvent.click(screen.getByText("Continuar"));
    await userEvent.click(screen.getByText("Agregar tarjeta"));
    await userEvent.type(screen.getByLabelText(/Nombre de la tarjeta 1/i), "Visa BBVA");
    await userEvent.type(screen.getByLabelText(/Cupo de la tarjeta 1/i), "5000000");
    await userEvent.type(screen.getByLabelText(/Día de corte de la tarjeta 1/i), "15");
    await userEvent.type(screen.getByLabelText(/Día de pago de la tarjeta 1/i), "5");
    await userEvent.click(screen.getByText("Finalizar"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onboardingMock).toHaveBeenCalledWith(
      { display_name: "Néstor", monthly_income: 30000, savings_goal_percentage: 20 },
      "tok",
    );
    expect(budgetMock).toHaveBeenCalledTimes(1);
    expect(budgetMock.mock.calls[0][0]).toMatchObject({
      category: "alimentacion",
      amount: 5000,
    });
    expect(cardMock).toHaveBeenCalledTimes(1);
    expect(cardMock.mock.calls[0][0]).toMatchObject({
      name: "Visa BBVA",
      credit_limit: 5000000,
      cutoff_day: 15,
      payment_day: 5,
    });
  });
});
