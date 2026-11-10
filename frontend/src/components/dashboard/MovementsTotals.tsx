"use client";

import { Fragment } from "react";

import { useMoney } from "@/context/CurrencyContext";
import type { MovementTotals } from "@/lib/movements";

interface MovementsTotalsProps {
  /** Which header to render: all movements, the cash chip, or one card chip. */
  mode: "all" | "cash" | "card";
  count: number;
  totals: MovementTotals;
}

const GOALS_LABEL = "Apartado para metas";

function Amount({ value, plus = false }: { value: number; plus?: boolean }) {
  const money = useMoney();
  // text-ink (not text-positive) keeps AA contrast at text-xs; the "+" sign is
  // what sets money coming back apart from the other amounts.
  return (
    <span className="font-semibold tabular-nums text-ink">
      {plus && "+"}
      {money(value)}
    </span>
  );
}

/** Header lines above the movements list: the figure the user compares with the
 *  Resumen, what it is made of, and goal flows (savings, not spending). */
export function MovementsTotals({ mode, count, totals }: MovementsTotalsProps) {
  const { expenses, paid, saved, withdrawn } = totals;

  if (mode === "all" || mode === "card") {
    return (
      <>
        <p className="text-xs text-muted">
          {count} movimiento(s) · gastado <Amount value={expenses} />
        </p>
        {mode === "all" && (
          <p className="text-xs text-muted">
            Igual a «Gastos» del Resumen. No incluye pagos a tarjetas ni movimientos de
            metas.
          </p>
        )}
        {mode === "all" && saved > 0 && (
          <p className="text-xs text-muted">
            Además apartaste <Amount value={saved} /> para metas (no es gasto).
          </p>
        )}
      </>
    );
  }

  // Cash chip: everything that left the available income, goals included (they
  // are savings, not gastos). Line by line the same as the Resumen "Flujo de caja".
  const parts: { label: string; value: number }[] = [
    { label: "Gastos en efectivo", value: expenses },
    { label: "Pagos a tarjetas", value: paid },
    { label: GOALS_LABEL, value: saved },
  ].filter((p) => p.value > 0);

  // A lone cash / payments part would just repeat the headline; a lone goals
  // part is kept so the user sees that the figure is money set aside.
  const showBreakdown = parts.length > 1 || parts[0]?.label === GOALS_LABEL;

  return (
    <>
      <p className="text-xs text-muted">
        {count} movimiento(s) · salió de tu caja{" "}
        <Amount value={expenses + paid + saved} />
      </p>
      {showBreakdown && (
        <p className="text-xs text-muted">
          {parts.map((part, i) => (
            <Fragment key={part.label}>
              {i > 0 && " · "}
              {part.label} <Amount value={part.value} />
            </Fragment>
          ))}
        </p>
      )}
      {withdrawn > 0 && (
        <p className="text-xs text-muted">
          Volvió de tus metas <Amount value={withdrawn} plus />
        </p>
      )}
      {paid > 0 && (
        <p className="text-xs text-muted">
          Los pagos a tarjetas cubren compras con tarjeta (normalmente de meses
          anteriores); por eso no se suman a lo gastado.
        </p>
      )}
      {saved > 0 && (
        <p className="text-xs text-muted">
          Lo apartado para metas es ahorro: sigue siendo tuyo, pero ya no está libre.
        </p>
      )}
    </>
  );
}
