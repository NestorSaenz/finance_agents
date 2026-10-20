"use client";

import { useMoney } from "@/context/CurrencyContext";
import type { MovementTotals } from "@/lib/movements";

interface MovementsTotalsProps {
  /** Which header to render: all movements, the cash chip, or one card chip. */
  mode: "all" | "cash" | "card";
  count: number;
  totals: MovementTotals;
}

function Amount({ value }: { value: number }) {
  const money = useMoney();
  return <span className="font-semibold tabular-nums text-ink">{money(value)}</span>;
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
      </>
    );
  }

  return (
    <>
      <p className="text-xs text-muted">
        {count} movimiento(s) · salió de tu bolsillo <Amount value={expenses + paid} />
      </p>
      {expenses > 0 && paid > 0 && (
        <p className="text-xs text-muted">
          Efectivo <Amount value={expenses} /> + pagos a tarjetas <Amount value={paid} />
        </p>
      )}
      {paid > 0 && (
        <p className="text-xs text-muted">
          Los pagos a tarjetas cubren compras con tarjeta (normalmente de meses
          anteriores); por eso no se suman a lo gastado.
        </p>
      )}
      {(saved > 0 || withdrawn > 0) && (
        <p className="text-xs text-muted">
          Metas (no es gasto):
          {saved > 0 && (
            <>
              {" "}guardaste <Amount value={saved} />
            </>
          )}
          {saved > 0 && withdrawn > 0 && " ·"}
          {withdrawn > 0 && (
            <>
              {" "}retiraste <Amount value={withdrawn} />
            </>
          )}
        </p>
      )}
    </>
  );
}
