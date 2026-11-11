"use client";

import { InfoDisclosure } from "@/components/ui/InfoDisclosure";
import { useMoney } from "@/context/CurrencyContext";
import type { HeroFigureData } from "@/lib/heroFigure";

interface HeroFigureProps {
  hero: HeroFigureData;
  income: number;
  /** Gastos = consumo + aportes (total_spent). */
  totalSpent: number;
  consumo: number;
  spentOnGoals: number;
  balance: number;
  /** Retiros reported by the endpoint (informational). */
  goalsReturned: number;
  /** Plan still to contribute this month; 0 hides the note. */
  pending: number;
}

// Big figure: large text passes at text-positive; the small stats need emerald-700 (AA).
const BIG_TONE: Record<"positive" | "negative", string> = {
  positive: "text-positive",
  negative: "text-negative",
};
const SMALL_TONE: Record<"positive" | "negative", string> = {
  positive: "text-emerald-700",
  negative: "text-negative",
};

/** One stat: a row (label left, amount right) on narrow screens, a column from
 *  440px up. The amount never wraps (the "$" stays with the digits). */
function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "positive" | "negative";
}) {
  const money = useMoney();
  return (
    <div className="flex items-baseline justify-between gap-3 min-[440px]:block">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p
        className={`whitespace-nowrap text-[15px] font-semibold tabular-nums min-[440px]:mt-0.5 ${SMALL_TONE[tone]}`}
      >
        {money(value)}
      </p>
    </div>
  );
}

/** The summary's lead card: one big figure with its bar, then Ingresos, Gastos and
 *  Balance, and one group with every note that qualifies those figures. Every value
 *  arrives computed; this only lays them out. */
export function HeroFigure({
  hero,
  income,
  totalSpent,
  consumo,
  spentOnGoals,
  balance,
  goalsReturned,
  pending,
}: HeroFigureProps) {
  const money = useMoney();
  const { bar } = hero;
  return (
    <section
      className="rounded-xl border border-line bg-surface p-4"
      aria-label="Cifra principal del resumen"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{hero.label}</p>
      <p className={`mt-1 break-words text-3xl font-bold tabular-nums ${BIG_TONE[hero.tone]}`}>
        {money(hero.value)}
      </p>
      <p className="mt-1 text-sm text-muted">{hero.subtitle}</p>

      {bar && (
        <div className="mt-3">
          <p className={`mb-1 text-xs font-medium ${bar.over ? "text-amber-700" : "text-ink"}`}>
            {bar.text}
          </p>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-label="Parte de tu ingreso que ya consumiste"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(bar.fill)}
            aria-valuetext={bar.valueText}
          >
            <div
              className={`h-full rounded-full transition-all ${bar.over ? "bg-amber-600" : "bg-brand-600"}`}
              style={{ width: `${bar.fill}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs tabular-nums text-muted">
            {money(bar.spent)} de {money(bar.income)}
          </p>
        </div>
      )}

      <div className="mt-4 flex flex-col gap-1.5 border-t border-line pt-3 min-[440px]:grid min-[440px]:grid-cols-3 min-[440px]:gap-3">
        <Stat label="Ingresos" value={income} tone="positive" />
        <Stat label="Gastos" value={totalSpent} tone="negative" />
        <Stat label="Balance" value={balance} tone={balance >= 0 ? "positive" : "negative"} />
      </div>

      {/* Everything that changes how the figures read, grouped and at one size. */}
      <div className="mt-3 flex flex-col gap-1 border-t border-line pt-3 text-xs text-muted">
        {hero.notes.map((note) => (
          <p key={note}>{note}</p>
        ))}
        {spentOnGoals > 0 && (
          <p>
            Gastos: consumo {money(consumo)} + metas {money(spentOnGoals)}
          </p>
        )}
        {pending > 0 && <p>Gastos sin contar {money(pending)} por aportar</p>}
        {goalsReturned > 0 && (
          <p>
            Además volvieron {money(goalsReturned)} de tus metas (no es ingreso; ya está en tu
            caja final).
          </p>
        )}
        <div className="flex flex-wrap items-center">
          <p className="min-w-0 flex-1">
            Balance: ingresos menos gastos del mes
            {spentOnGoals > 0 ? " (incluye lo apartado a metas)" : ""}.
          </p>
          <InfoDisclosure label="Balance">
            Los cargos a crédito cuentan completos, aunque aún no los pagues — por eso puede
            diferir de tu caja real.
          </InfoDisclosure>
        </div>
      </div>
    </section>
  );
}
