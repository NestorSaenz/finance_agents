"use client";

import { formatMoney } from "@/lib/format";
import { planFill, planTotals, visiblePlans } from "@/lib/goalPlans";
import type { GoalPlanStatus, GoalPlanStatusList } from "@/lib/types";

/** Saving colours are inverted vs spending: never red; green once the plan is
 *  reached, the brand tone otherwise. */
function PlanRow({ status: s }: { status: GoalPlanStatus }) {
  const fill = planFill(s);
  const met = s.is_met;
  const saved = Number(s.contributed_gross);
  const withdrawn = Number(s.withdrawn);
  return (
    <li>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5 text-sm">
        <span className="min-w-0 break-words text-ink">{s.goal_name}</span>
        <span className="text-xs tabular-nums text-muted">
          aportado {formatMoney(saved, s.currency)} de{" "}
          {formatMoney(s.effective_planned, s.currency)}
        </span>
      </div>
      <div
        className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        aria-label={`Plan de ${s.goal_name}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fill)}
        aria-valuetext={`aportado ${formatMoney(saved, s.currency)} de ${formatMoney(s.effective_planned, s.currency)}`}
      >
        <div
          className={`h-full rounded-full transition-all ${met ? "bg-positive" : "bg-brand-600"}`}
          style={{ width: `${fill}%` }}
        />
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-ink">
          {met ? "✓ cumplido" : `faltan ${formatMoney(s.remaining, s.currency)}`}
        </span>
        {s.goal_completed && (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-ink">
            meta completada
          </span>
        )}
        {withdrawn > 0 && <span>retiraste {formatMoney(withdrawn, s.currency)}</span>}
      </div>
    </li>
  );
}

/** "Ahorro planificado · no es gasto": one row per goal planned this month plus a
 *  total line per currency. Renders nothing when no goal has a plan. */
export function GoalPlanProgress({ data }: { data: GoalPlanStatusList | null }) {
  if (!data) return null;
  const plans = visiblePlans(data);
  if (plans.length === 0) return null;
  const totals = planTotals(data);

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">
        Ahorro planificado · no es gasto
      </p>
      <ul className="mt-3 flex flex-col gap-3">
        {plans.map((s) => (
          <PlanRow key={s.goal_id} status={s} />
        ))}
      </ul>
      <div className="mt-3 flex flex-col gap-0.5 border-t border-line pt-2 text-xs text-muted">
        {totals.map((t) => (
          <p key={t.currency}>
            Planeado{" "}
            <span className="font-semibold tabular-nums text-ink">
              {formatMoney(t.planned, t.currency)}
            </span>{" "}
            · aportado{" "}
            <span className="font-semibold tabular-nums text-ink">
              {formatMoney(t.saved, t.currency)}
            </span>
          </p>
        ))}
      </div>
    </div>
  );
}
