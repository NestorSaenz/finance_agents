import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingWizard } from "./OnboardingWizard";

const { onboardingMock, budgetMock, cardMock, recurringMock } = vi.hoisted(() => ({
  onboardingMock: vi.fn(),
  budgetMock: vi.fn(),
  cardMock: vi.fn(),
  recurringMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    completeOnboarding: (...args: unknown[]) => onboardingMock(...args),
    createBudget: (...args: unknown[]) => budgetMock(...args),
    createCard: (...args: unknown[]) => cardMock(...args),
    createRecurring: (...args: unknown[]) => recurringMock(...args),
  },
}));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ token: "tok" }),
}));

beforeEach(() => {
  onboardingMock.mockReset().mockResolvedValue({});
  budgetMock.mockReset().mockResolvedValue({});
  cardMock.mockReset().mockResolvedValue({});
  recurringMock.mockReset().mockResolvedValue({});
});

describe("OnboardingWizard", () => {
  it("skips without sending income", async () => {
    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);

    await userEvent.click(screen.getByText("Omitir"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onboardingMock).toHaveBeenCalledWith(
      expect.objectContaining({
        display_name: undefined,
        monthly_income: undefined,
        savings_goal_percentage: undefined,
        currency: "COP",
      }),
      "tok",
    );
    expect(budgetMock).not.toHaveBeenCalled();
    expect(recurringMock).not.toHaveBeenCalled();
  });

  it("sends the currency chosen in the onboarding picker", async () => {
    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);

    await userEvent.selectOptions(
      screen.getByLabelText("Moneda"),
      "USD",
    );
    await userEvent.click(screen.getByText("Omitir"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onboardingMock.mock.calls[0][0]).toMatchObject({ currency: "USD" });
  });

  it("auto-detects and sends the browser timezone silently", async () => {
    // Make the detected timezone deterministic regardless of the CI host.
    const resolvedOptions = vi
      .spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions")
      .mockReturnValue({ timeZone: "America/Bogota" } as Intl.ResolvedDateTimeFormatOptions);

    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);

    // No timezone UI exists — detection is silent.
    expect(screen.queryByText(/zona horaria/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Omitir"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onboardingMock.mock.calls[0][0]).toMatchObject({
      timezone: "America/Bogota",
    });

    resolvedOptions.mockRestore();
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
    // Step 2 -> step 3 (cards): add a card and continue.
    await userEvent.click(screen.getByText("Continuar"));
    await userEvent.click(screen.getByText("Agregar tarjeta"));
    await userEvent.type(screen.getByLabelText(/Nombre de la tarjeta 1/i), "Visa BBVA");
    await userEvent.type(screen.getByLabelText(/Cupo de la tarjeta 1/i), "5000000");
    await userEvent.type(screen.getByLabelText(/Día de corte de la tarjeta 1/i), "15");
    await userEvent.type(screen.getByLabelText(/Día de pago de la tarjeta 1/i), "5");
    // Step 3 -> step 4 (movimientos fijos), then finish without adding any.
    await userEvent.click(screen.getByText("Continuar"));
    await userEvent.click(screen.getByText("Finalizar"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onboardingMock).toHaveBeenCalledWith(
      expect.objectContaining({
        display_name: "Néstor",
        monthly_income: 30000,
        savings_goal_percentage: 20,
        currency: "COP",
      }),
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
    // No fixed movements were added on the last step.
    expect(recurringMock).not.toHaveBeenCalled();
  });

  /** Advance from the welcome step to the fixed-movements step (step 4). */
  async function goToRecurringStep() {
    await userEvent.click(screen.getByText("Continuar")); // step 1 -> 2
    await userEvent.click(screen.getByText("Continuar")); // step 2 -> 3
    await userEvent.click(screen.getByText("Continuar")); // step 3 -> 4
  }

  it("creates a fixed movement on finish", async () => {
    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);

    await goToRecurringStep();

    await userEvent.click(screen.getByText("Agregar movimiento"));
    await userEvent.type(
      screen.getByLabelText(/Descripción del movimiento 1/i),
      "Sueldo",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ingreso" }));
    await userEvent.type(screen.getByLabelText(/Monto del movimiento 1/i), "1000000");
    await userEvent.type(screen.getByLabelText(/Día del mes del movimiento 1/i), "1");
    await userEvent.click(screen.getByText("Finalizar"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(recurringMock).toHaveBeenCalledTimes(1);
    expect(recurringMock.mock.calls[0][0]).toEqual({
      description: "Sueldo",
      amount: 1000000,
      transaction_type: "income",
      day_of_month: 1,
    });
  });

  it("does not create fixed movements when the last step is skipped", async () => {
    const onDone = vi.fn();
    render(<OnboardingWizard onDone={onDone} />);

    await goToRecurringStep();

    // Fill a row but click "Omitir" instead of "Finalizar".
    await userEvent.click(screen.getByText("Agregar movimiento"));
    await userEvent.type(
      screen.getByLabelText(/Descripción del movimiento 1/i),
      "Sueldo",
    );
    await userEvent.type(screen.getByLabelText(/Monto del movimiento 1/i), "1000000");
    await userEvent.type(screen.getByLabelText(/Día del mes del movimiento 1/i), "1");
    await userEvent.click(screen.getByText("Omitir"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(recurringMock).not.toHaveBeenCalled();
  });
});
