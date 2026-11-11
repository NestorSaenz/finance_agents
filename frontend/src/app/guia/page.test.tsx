import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import GuiaPage from "./page";

describe("GuiaPage", () => {
  it("renders the hero headline", () => {
    render(<GuiaPage />);

    const heading = screen.getByRole("heading", { level: 1 });
    // The headline is split across a <br> + gradient span: "Tu dinero," / "hablando.".
    expect(heading).toHaveTextContent("Tu dinero,");
    expect(heading).toHaveTextContent("hablando.");
  });

  it("renders the chapter headings", () => {
    render(<GuiaPage />);

    expect(screen.getByRole("heading", { name: "Aparta, retira, ajusta" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Lo de todos los meses, en automático" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Todo lo que puedes hacer" }),
    ).toBeInTheDocument();
  });

  it("renders the capabilities cloud items", () => {
    render(<GuiaPage />);

    expect(screen.getByText("Metas: aportar, retirar, ajustar")).toBeInTheDocument();
    expect(screen.getByText("Movimientos fijos (recurrentes)")).toBeInTheDocument();
    expect(screen.getByText("Tu caja real del mes (flujo de caja)")).toBeInTheDocument();
  });

  it("renders the dashboard peek with the real available amount", () => {
    render(<GuiaPage />);

    // The cash-flow peek now separates spending from saving.
    expect(screen.getByText("Te sobró")).toBeInTheDocument();
    expect(screen.getByText("Caja final del mes")).toBeInTheDocument();
    expect(screen.getByText("Flujo de caja · este mes")).toBeInTheDocument();
  });

  it("renders the closing CTA", () => {
    render(<GuiaPage />);

    expect(screen.getByRole("heading", { name: "Solo escríbele." })).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: "Crear cuenta gratis" });
    expect(cta).toHaveAttribute("href", "/signup");
  });
});

describe("GuiaPage - plan mensual, validación de extractos y cambio de corte", () => {
  it("lists the new capabilities", () => {
    render(<GuiaPage />);

    expect(screen.getByText("Plan mensual de metas")).toBeInTheDocument();
    expect(screen.getByText("Validar extractos contra lo registrado")).toBeInTheDocument();
    expect(screen.getByText("Cambio de corte con confirmación")).toBeInTheDocument();
  });

  it("documents the goal plan, the statement validation and the cutoff change", () => {
    render(<GuiaPage />);

    expect(
      screen.getByText("para noviembre aparta 500.000 a la meta de vacaciones"),
    ).toBeInTheDocument();
    expect(screen.getByText(/valida que todos estos movimientos de Nu/)).toBeInTheDocument();
    expect(screen.getByText("cambia el corte de Rappi al 20")).toBeInTheDocument();
    expect(screen.getAllByText(/Por aportar a tus metas este mes \(plan\)/).length).toBeGreaterThan(0);
  });
});

describe("GuiaPage - exactitud de los ejemplos de metas", () => {
  it("the contribution example uses 'abona' (a contribution), never 'aparta' (a plan)", () => {
    render(<GuiaPage />);

    expect(screen.getByText("abona 200.000 al viaje a Japón")).toBeInTheDocument();
    expect(screen.queryByText("aparta 200.000 para el viaje a Japón")).toBeNull();
  });

  it("a contribution is described as counting in the month's expenses", () => {
    render(<GuiaPage />);

    // The reply to a real contribution says it counts; only the PLAN is "no es gasto".
    expect(screen.getAllByText(/cuenta en tus gastos del mes como ahorro/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/aporte[^.]*no es gasto/i)).toBeNull();
  });

  it("the plan examples name the goal and their numbers line up", () => {
    render(<GuiaPage />);

    expect(
      screen.getByText("quita el plan de diciembre del fondo de emergencias"),
    ).toBeInTheDocument();
    expect(screen.getByText(/aportado.*\(40%\)/)).toBeInTheDocument();
  });
});
