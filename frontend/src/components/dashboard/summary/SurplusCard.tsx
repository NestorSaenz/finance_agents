"use client";

import { useMoney } from "@/context/CurrencyContext";

/** "Excedente acumulado": free cash carried over month to month (from the backend). */
export function SurplusCard({ accumulatedSurplus }: { accumulatedSurplus: number }) {
  const money = useMoney();
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">
        Excedente acumulado
      </p>
      <p
        className={`mt-1 text-2xl font-semibold ${
          accumulatedSurplus >= 0 ? "text-positive" : "text-negative"
        }`}
      >
        {money(accumulatedSurplus)}
      </p>
      <p className="mt-2 text-xs text-muted">
        Tu plata libre acumulada, mes a mes. Baja cuando gastas o aportas a metas.
      </p>
    </div>
  );
}
