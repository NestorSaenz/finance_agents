"use client";

import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { planFill, planTotals, visiblePlans } from "@/lib/goalPlans";
import type { GoalPlanStatus, GoalPlanStatusList } from "@/lib/types";

/** Plans shown before the "Ver todas" toggle. */
const COLLAPSED_COUNT = 4;

/** Two lines per goal. Saving colours are inverted vs spending: never red; green
 *  once the plan is reached, the brand tone otherwise. */
function PlanRow({ status: s, currency }: { status: GoalPlanStatus; currency: string }) {
  const fill = planFill(s);
  const saved = formatMoney(s.contributed_gross, currency);
  const planned = formatMoney(s.effective_planned, currency);
  const withdrawn = Number(s.withdrawn);
  return (
    <li>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 text-sm">
        <span className="min-w-0 break-words text-ink">{s.goal_name}</span>
        <span className="text-xs tabular-nums text-muted">
          {saved} / {planned}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
        <div
          className="h-2 min-w-[6rem] flex-1 overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-label={`Plan de ${s.goal_name}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(fill)}
          aria-valuetext={`aportado ${saved} de ${planned}`}
        >
          <div
            className={`h-full rounded-full transition-all ${
              s.is_met ? "bg-positive" : "bg-brand-600"
            }`}
            style={{ width: `${fill}%` }}
          />
        </div>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-ink">
          {s.is_met ? "✓ cumplido" : `faltan ${formatMoney(s.remaining, currency)}`}
        </span>
        {s.goal_completed && (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-ink">
            meta completada
          </span>
        )}
        {withdrawn > 0 && (
          <span className="text-xs text-muted">
            retiraste {formatMoney(withdrawn, currency)}
          </span>
        )}
      </div>
    </li>
  );
}

/** "Ahorro planificado del mes": one compact row per goal planned in the chosen
 *  month (first 4, then "Ver todas") plus a total line per currency. Renders
 *  nothing when no goal has a plan. */
export function GoalPlanProgress({
  data,
  displayCurrency,
}: {
  data: GoalPlanStatusList | null;
  /** The profile currency. Used for every amount when all plans share ONE
   *  currency (a goal labelled differently is still the user's money); with
   *  several currencies each keeps its own. */
  displayCurrency?: string;
}) {
  const [showAll, setShowAll] = useState(false);
  if (!data) return null;
  const plans = visiblePlans(data);
  if (plans.length === 0) return null;
  const totals = planTotals(data);
  const single = new Set(plans.map((p) => p.currency)).size === 1;
  const cur = (own: string): string => (single && displayCurrency ? displayCurrency : own);
  const shown = showAll ? plans : plans.slice(0, COLLAPSED_COUNT);

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">
        Ahorro planificado del mes
      </p>
      <p className="mt-0.5 text-xs text-muted">
        El plan no es gasto; lo que aportes sí cuenta en tus gastos del mes
      </p>
      <ul className="mt-3 flex flex-col gap-3">
        {shown.map((s) => (
          <PlanRow key={s.goal_id} status={s} currency={cur(s.currency)} />
        ))}
      </ul>
      {plans.length > COLLAPSED_COUNT && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          aria-expanded={showAll}
          className="mt-1 inline-flex min-h-[44px] items-center rounded-md text-xs font-medium text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
        >
          {showAll ? "Ver menos" : `Ver todas (${plans.length})`}
        </button>
      )}
      <div className="mt-2 flex flex-col gap-0.5 border-t border-line pt-2 text-xs text-muted">
        {totals.map((t) => (
          <p key={t.currency}>
            Planeado{" "}
            <span className="font-semibold tabular-nums text-ink">
              {formatMoney(t.planned, cur(t.currency))}
            </span>{" "}
            · aportado{" "}
            <span className="font-semibold tabular-nums text-ink">
              {formatMoney(t.saved, cur(t.currency))}
            </span>
          </p>
        ))}
      </div>
    </div>
  );
}
