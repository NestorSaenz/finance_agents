"use client";

import { useMoney } from "@/context/CurrencyContext";

interface PaymentSplitProps {
  credit: number;
  cash: number;
  totalExpenses: number;
}

/** Credit vs cash (vs unspecified) distribution of expenses as a split bar. */
export function PaymentSplit({ credit, cash, totalExpenses }: PaymentSplitProps) {
  const money = useMoney();
  const unspecified = Math.max(totalExpenses - credit - cash, 0);
  const total = credit + cash + unspecified;
  if (total <= 0) return null;

  const pct = (v: number) => (v / total) * 100;
  const segments = [
    { label: "Crédito", value: credit, color: "#0d9488" },
    { label: "Efectivo", value: cash, color: "#5eead4" },
    { label: "Sin especificar", value: unspecified, color: "#cbd5e1" },
  ].filter((s) => s.value > 0);

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
        Cómo pagas
      </p>

      <div className="flex h-3 w-full overflow-hidden rounded-full">
        {segments.map((s) => (
          <div
            key={s.label}
            style={{ width: `${pct(s.value)}%`, backgroundColor: s.color }}
            title={`${s.label}: ${money(s.value)}`}
          />
        ))}
      </div>

      <div className="mt-3 flex flex-col gap-1.5">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-2 text-sm">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ backgroundColor: s.color }}
              aria-hidden
            />
            <span className="text-muted">{s.label}</span>
            <span className="ml-auto font-medium text-ink">{money(s.value)}</span>
            <span className="w-10 text-right text-xs text-muted">
              {pct(s.value).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
