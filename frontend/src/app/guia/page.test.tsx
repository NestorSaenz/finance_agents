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
    expect(screen.getByText("Disponible real (flujo de caja)")).toBeInTheDocument();
  });

  it("renders the dashboard peek with the real available amount", () => {
    render(<GuiaPage />);

    expect(screen.getByText("Disponible real")).toBeInTheDocument();
    expect(screen.getByText("Flujo de caja · este mes")).toBeInTheDocument();
  });

  it("renders the closing CTA", () => {
    render(<GuiaPage />);

    expect(screen.getByRole("heading", { name: "Solo escríbele." })).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: "Crear cuenta gratis" });
    expect(cta).toHaveAttribute("href", "/signup");
  });
});
