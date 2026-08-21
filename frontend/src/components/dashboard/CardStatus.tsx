"use client";

import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";

import { useMoney } from "@/context/CurrencyContext";
import { categoryLabel, formatDayMonth } from "@/lib/format";
import type {
  CardPaymentItem,
  CreditCardStatusList,
  Transaction,
} from "@/lib/types";

/** Colour the debt bar by how much of the limit is used. */
function barTone(pct: number): string {
  if (pct >= 90) return "bg-negative";
  if (pct >= 70) return "bg-amber-500";
  return "bg-brand-600";
}

/** "Compras de julio de 2026" for a pinned month, else "Compras del mes" for the
 *  current/relative views where no specific month is selected. */
function chargesHeading(period: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(period);
  if (!match) return "Compras del mes";
  const d = new Date(Number(match[1]), Number(match[2]) - 1, 1);
  return `Compras de ${d.toLocaleDateString("es-ES", { month: "long", year: "numeric" })}`;
}

function pushInto<T>(map: Map<string, T[]>, key: string, value: T): void {
  const bucket = map.get(key);
  if (bucket) bucket.push(value);
  else map.set(key, [value]);
}

interface CardStatusProps {
  data: CreditCardStatusList;
  /** Viewing a past month: figures are reconstructed at that month-end. */
  historical?: boolean;
  /** This period's transactions — a card's charges are filtered from these. */
  transactions: Transaction[];
  /** This period's card payments (already carry card_id). */
  payments: CardPaymentItem[];
  /** The selected period, to label the charges heading ("Compras de julio…"). */
  period: string;
}

export function CardStatus({
  data,
  historical = false,
  transactions,
  payments,
  period,
}: CardStatusProps) {
  // One card's detail expands at a time (classic accordion), keeping the panel tidy.
  const [openId, setOpenId] = useState<string | null>(null);

  // Group charges/payments by card ONCE, so each row just reads its slice.
  const chargesByCard = useMemo(() => {
    const map = new Map<string, Transaction[]>();
    for (const tx of transactions) {
      if (tx.transaction_type === "expense" && tx.card_id) pushInto(map, tx.card_id, tx);
    }
    return map;
  }, [transactions]);

  const paymentsByCard = useMemo(() => {
    const map = new Map<string, CardPaymentItem[]>();
    for (const p of payments) pushInto(map, p.card_id, p);
    return map;
  }, [payments]);

  if (data.cards.length === 0) return null;

  const heading = chargesHeading(period);

  return (
    <div className="flex flex-col gap-3">
      {data.cards.map((c) => (
        <CardStatusRow
          key={c.card.id}
          status={c}
          historical={historical}
          heading={heading}
          charges={chargesByCard.get(c.card.id) ?? []}
          payments={paymentsByCard.get(c.card.id) ?? []}
          isOpen={openId === c.card.id}
          onToggle={() =>
            setOpenId((id) => (id === c.card.id ? null : c.card.id))
          }
        />
      ))}
    </div>
  );
}

function CardStatusRow({
  status: c,
  historical,
  heading,
  charges,
  payments,
  isOpen,
  onToggle,
}: {
  status: CreditCardStatusList["cards"][number];
  historical: boolean;
  heading: string;
  charges: Transaction[];
  payments: CardPaymentItem[];
  isOpen: boolean;
  onToggle: () => void;
}) {
  const money = useMoney();
  const pct = c.utilization;
  const hasStatement = charges.length > 0 || payments.length > 0;
  const regionId = `card-stmt-${c.card.id}`;

  // Disclosure toggle carries ONLY phrasing content (name + chevron); the
  // progress bar and the summary <dl> stay static outside the button.
  const header = (
    <>
      <span className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-sm font-semibold text-ink">{c.card.name}</span>
        {hasStatement && (
          <ChevronDown
            className={`h-4 w-4 shrink-0 text-muted transition-transform motion-reduce:transition-none ${
              isOpen ? "rotate-180" : ""
            }`}
            aria-hidden
          />
        )}
      </span>
      <span className="shrink-0 text-xs text-muted">
        Corte {c.card.cutoff_day} · Pago {c.card.payment_day}
      </span>
    </>
  );

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      {hasStatement ? (
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isOpen}
          // Only reference the region while it's actually in the DOM (rendered on open).
          aria-controls={isOpen ? regionId : undefined}
          aria-label={`Ver movimientos de ${c.card.name}`}
          className="-my-1 flex w-full items-baseline justify-between gap-2 rounded-md py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
        >
          {header}
        </button>
      ) : (
        <div className="flex items-baseline justify-between gap-2">{header}</div>
      )}

      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all ${barTone(pct)}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>

      <p className="mt-2 text-sm text-ink">
        <span className="font-semibold">{money(c.balance)}</span>
        <span className="text-muted"> de deuda / {money(c.card.credit_limit)}</span>
      </p>

      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted">Disponible</dt>
        <dd className="text-right font-medium text-positive">{money(c.available)}</dd>
        <dt className="text-muted">Gastado en el mes</dt>
        <dd className="text-right text-ink">{money(c.spent_cycle)}</dd>
        <dt className="text-muted">{historical ? "Fecha de pago" : "Próximo pago"}</dt>
        <dd className="text-right text-ink">{formatDayMonth(c.next_payment_date)}</dd>
      </dl>

      {hasStatement && isOpen && (
        <CardStatement
          id={regionId}
          cardName={c.card.name}
          heading={heading}
          charges={charges}
          payments={payments}
        />
      )}
    </div>
  );
}

/** The expandable per-card mini statement: this month's charges and the payments
 *  made to the card, each with a subtotal. */
function CardStatement({
  id,
  cardName,
  heading,
  charges,
  payments,
}: {
  id: string;
  cardName: string;
  heading: string;
  charges: Transaction[];
  payments: CardPaymentItem[];
}) {
  const money = useMoney();
  const sortedCharges = useMemo(
    () => [...charges].sort((a, b) => (a.transaction_date < b.transaction_date ? 1 : -1)),
    [charges],
  );
  const sortedPayments = useMemo(
    () => [...payments].sort((a, b) => (a.payment_date < b.payment_date ? 1 : -1)),
    [payments],
  );
  const chargesTotal = sortedCharges.reduce((s, t) => s + Number(t.amount), 0);
  const paymentsTotal = sortedPayments.reduce((s, p) => s + Number(p.amount), 0);

  return (
    <div
      id={id}
      role="region"
      aria-label={`Movimientos de ${cardName}`}
      className="mt-3 border-t border-line pt-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-muted">
        {sortedCharges.length > 0 && (
          <span>
            {heading}{" "}
            <span className="font-semibold text-negative">−{money(chargesTotal)}</span>
          </span>
        )}
        {sortedPayments.length > 0 && (
          <span>
            Pagos{" "}
            <span className="font-semibold text-positive">+{money(paymentsTotal)}</span>
          </span>
        )}
      </div>

      <ul className="mt-2 flex flex-col gap-2">
        {sortedCharges.map((tx) => (
          <StatementRow
            key={`charge-${tx.id}`}
            title={tx.description}
            meta={`${categoryLabel(tx.category)} · ${formatDayMonth(tx.transaction_date)}`}
            amount={tx.amount}
          />
        ))}
        {sortedPayments.map((p, i) => (
          <StatementRow
            key={`payment-${i}-${p.payment_date}`}
            title="Pago a la tarjeta"
            meta={`Abono · ${formatDayMonth(p.payment_date)}`}
            amount={p.amount}
            isInflow
          />
        ))}
      </ul>

      {sortedCharges.length > 0 && (
        <p className="mt-2 text-[11px] text-muted">
          Compras por fecha de compra; “Gastado en el mes” sigue tu ciclo de corte, así
          que pueden no coincidir.
        </p>
      )}
    </div>
  );
}

function StatementRow({
  title,
  meta,
  amount,
  isInflow = false,
}: {
  title: string;
  meta: string;
  amount: string;
  isInflow?: boolean;
}) {
  const money = useMoney();
  return (
    <li className="flex items-start justify-between gap-3 text-sm">
      <div className="min-w-0">
        <p className="truncate text-ink">{title}</p>
        <p className="text-xs text-muted">{meta}</p>
      </div>
      <p
        className={`shrink-0 font-medium tabular-nums ${
          isInflow ? "text-positive" : "text-negative"
        }`}
      >
        {isInflow ? "+" : "−"}
        {money(amount)}
      </p>
    </li>
  );
}
