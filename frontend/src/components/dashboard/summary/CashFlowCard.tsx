"use client";

import { useMoney } from "@/context/CurrencyContext";

interface CashFlowCardProps {
  income: number;
  cashExpenses: number;
  cardPayments: number;
  /** Gross aportes / retiros of the period (never netted). */
  goalSaved: number;
  goalWithdrawn: number;
  hasGoalFlow: boolean;
  afterSpending: number;
  cashAvailable: number;
  /** Plan still to contribute this month (informational) and the figures it implies. */
  pending: number;
  hasPending: boolean;
  afterPending: number;
  totalSpent: number;
  note: string;
}

/** "Flujo de caja": income minus what really left the pocket, goals apart, and the
 *  informational "Por aportar" lines. All values arrive already computed. */
export function CashFlowCard({
  income,
  cashExpenses,
  cardPayments,
  goalSaved,
  goalWithdrawn,
  hasGoalFlow,
  afterSpending,
  cashAvailable,
  pending,
  hasPending,
  afterPending,
  totalSpent,
  note,
}: CashFlowCardProps) {
  const money = useMoney();
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">
        Flujo de caja
      </p>
      <dl className="mt-2 flex flex-col gap-1 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-muted">Ingresos</dt>
          <dd className="tabular-nums text-positive">{money(income)}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-muted">Efectivo</dt>
          <dd className="tabular-nums text-negative">−{money(cashExpenses)}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-muted">Pagos a tarjetas</dt>
          <dd className="tabular-nums text-negative">−{money(cardPayments)}</dd>
        </div>

        {/* Subtotal after money that ACTUALLY left the pocket. When there are
            no goal movements this is already the bottom line. */}
        <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5">
          <dt className="font-medium text-ink">
            {hasGoalFlow
              ? afterSpending >= 0
                ? "Te sobró"
                : "Te faltó"
              : "Disponible del mes"}
          </dt>
          <dd
            className={`font-semibold tabular-nums ${
              afterSpending >= 0 ? "text-positive" : "text-negative"
            }`}
          >
            {money(afterSpending)}
          </dd>
        </div>

        {/* Saving is NOT spending: goal money apart in a neutral tone, then
            the final cash position after choosing to save. */}
        {hasGoalFlow && (
          <>
            {goalSaved > 0 && (
              <div className="flex items-center justify-between">
                <dt className="text-muted">Apartado para metas</dt>
                <dd className="tabular-nums text-brand-600">−{money(goalSaved)}</dd>
              </div>
            )}
            {goalWithdrawn > 0 && (
              <div className="flex items-center justify-between">
                <dt className="text-muted">Retirado de metas</dt>
                <dd className="tabular-nums text-positive">+{money(goalWithdrawn)}</dd>
              </div>
            )}
            <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5">
              <dt className="font-medium text-ink">Caja final del mes</dt>
              <dd
                className={`font-semibold tabular-nums ${
                  cashAvailable >= 0 ? "text-positive" : "text-amber-700"
                }`}
              >
                {money(cashAvailable)}
              </dd>
            </div>
          </>
        )}
      </dl>
      {hasPending && (
        <div className="mt-3 flex flex-col gap-0.5 border-t border-line pt-2 text-xs text-muted">
          <p>
            Por aportar a tus metas este mes (plan):{" "}
            <span className="font-semibold tabular-nums text-ink">{money(pending)}</span>
          </p>
          <p>
            {afterPending >= 0 ? (
              <>
                Si lo aportas, tu caja final quedaría en{" "}
                <span className="font-semibold tabular-nums text-ink">
                  {money(afterPending)}
                </span>
              </>
            ) : (
              <>
                Si lo aportas, te faltarían{" "}
                <span className="font-semibold tabular-nums text-amber-700">
                  {money(Math.abs(afterPending))}
                </span>
              </>
            )}{" "}
            y tus gastos del mes subirían a{" "}
            <span className="font-semibold tabular-nums text-ink">
              {money(totalSpent + pending)}
            </span>
          </p>
          <p>Es un plan: no cuenta como gasto hasta que registres el aporte.</p>
        </div>
      )}
      <p className="mt-2 text-xs text-muted">{note}</p>
    </div>
  );
}
