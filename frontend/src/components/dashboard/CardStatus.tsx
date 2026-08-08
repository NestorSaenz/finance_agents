"use client";

import { formatDayMonth, formatMoney } from "@/lib/format";
import type { CreditCardStatusList } from "@/lib/types";

/** Colour the debt bar by how much of the limit is used. */
function toneFor(pct: number): { bar: string; text: string } {
  if (pct >= 90) return { bar: "bg-negative", text: "text-negative" };
  if (pct >= 70) return { bar: "bg-amber-500", text: "text-amber-600" };
  return { bar: "bg-brand-600", text: "text-muted" };
}

export function CardStatus({
  data,
  historical = false,
}: {
  data: CreditCardStatusList;
  /** Viewing a past month: figures are reconstructed at that month-end. */
  historical?: boolean;
}) {
  if (data.cards.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      {data.cards.map((c) => {
        const pct = c.utilization;
        const tone = toneFor(pct);
        return (
          <div key={c.card.id} className="rounded-xl border border-line bg-surface p-4">
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <p className="truncate text-sm font-semibold text-ink">{c.card.name}</p>
              <p className="shrink-0 text-xs text-muted">
                Corte {c.card.cutoff_day} · Pago {c.card.payment_day}
              </p>
            </div>

            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-all ${tone.bar}`}
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>

            <p className="mt-2 text-sm text-ink">
              <span className="font-semibold">{formatMoney(c.balance)}</span>
              <span className="text-muted"> de deuda / {formatMoney(c.card.credit_limit)}</span>
            </p>

            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <dt className="text-muted">Disponible</dt>
              <dd className="text-right font-medium text-positive">
                {formatMoney(c.available)}
              </dd>
              <dt className="text-muted">Gastado en el mes</dt>
              <dd className="text-right text-ink">{formatMoney(c.spent_cycle)}</dd>
              <dt className="text-muted">{historical ? "Fecha de pago" : "Próximo pago"}</dt>
              <dd className="text-right text-ink">{formatDayMonth(c.next_payment_date)}</dd>
            </dl>
          </div>
        );
      })}
    </div>
  );
}
