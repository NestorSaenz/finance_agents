"use client";

import { InfoDisclosure } from "@/components/ui/InfoDisclosure";
import { useMoney } from "@/context/CurrencyContext";

/** Compact "Excedente acumulado" row; its definition sits behind the "i". */
export function SurplusCompact({ accumulatedSurplus }: { accumulatedSurplus: number }) {
  const money = useMoney();
  return (
    <div className="flex flex-wrap items-center gap-x-2 rounded-xl border border-line bg-surface py-1 pl-4 pr-1">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">Excedente acumulado</p>
      <p
        className={`ml-auto text-base font-semibold tabular-nums ${
          accumulatedSurplus >= 0 ? "text-positive" : "text-negative"
        }`}
      >
        {money(accumulatedSurplus)}
      </p>
      <InfoDisclosure label="Excedente acumulado">
        <span className="block pb-3 pr-3">
          Tu plata libre acumulada, mes a mes. Baja cuando gastas o aportas a metas.
        </span>
      </InfoDisclosure>
    </div>
  );
}
