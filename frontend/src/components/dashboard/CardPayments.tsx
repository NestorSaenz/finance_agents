"use client";

import { useMoney } from "@/context/CurrencyContext";
import { formatDayMonth } from "@/lib/format";
import type { CardPaymentsList } from "@/lib/types";

/** Card payments made in the period, shown as events (they reduce debt, not
 *  category spending — so they'd otherwise only appear as the balance going
 *  down). */
export function CardPayments({ data }: { data: CardPaymentsList }) {
  const money = useMoney();
  if (data.payments.length === 0) return null;

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      {data.payments.map((p, index) => (
        <div
          key={`${p.card_name}-${p.payment_date}-${p.amount}-${index}`}
          className="flex items-baseline justify-between gap-2 py-1 text-sm"
        >
          <span className="truncate text-ink">{p.card_name}</span>
          <span className="flex shrink-0 items-baseline gap-2">
            <span className="text-xs text-muted">{formatDayMonth(p.payment_date)}</span>
            <span className="font-medium text-positive">{money(p.amount)}</span>
          </span>
        </div>
      ))}
      <div className="mt-2 flex items-baseline justify-between border-t border-line pt-2 text-sm">
        <span className="text-muted">Total pagado</span>
        <span className="font-semibold text-ink">{money(data.total)}</span>
      </div>
    </div>
  );
}
