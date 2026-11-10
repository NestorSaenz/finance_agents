"use client";

import { useMoney } from "@/context/CurrencyContext";
import type { BudgetIncomeShare, PlanIncomeShare } from "@/lib/budgets";
import { formatPercent } from "@/lib/format";

function Strong({ children }: { children: React.ReactNode }) {
  return <span className="font-semibold tabular-nums text-ink">{children}</span>;
}

interface BudgetIncomeSummaryProps {
  /** Topes vs income; null when there are no topes (e.g. a past month). */
  share: BudgetIncomeShare | null;
  /** The month's planned goal saving vs income (a plan is not a gasto or a tope). */
  plan?: PlanIncomeShare | null;
}

/** What share of the base income the topes occupy: the monthly category total,
 *  the overall tope apart, and a calm note when they exceed the income. Planned
 *  goal saving gets its own lines below. Renders nothing when there is nothing to
 *  report. */
export function BudgetIncomeSummary({ share, plan = null }: BudgetIncomeSummaryProps) {
  const money = useMoney();
  const hasTopes = share !== null && (share.categoryTotal > 0 || share.overall !== null);
  if (!hasTopes && !plan) return null;

  return (
    <div className="flex flex-col gap-0.5 text-xs text-muted">
      {share && share.categoryTotal > 0 && (
        <p>
          Tus topes suman <Strong>{money(share.categoryTotal)}</Strong> ·{" "}
          <Strong>{formatPercent(share.totalPct)}</Strong> de tu ingreso
        </p>
      )}
      {share?.overall && (
        <p>
          Tope general <Strong>{money(share.overall.amount)}</Strong> ·{" "}
          <Strong>{formatPercent(share.overall.pct)}</Strong> de tu ingreso (aparte del
          total)
        </p>
      )}
      {share && share.totalPct > 100 && (
        <p>Tus topes suman más que tu ingreso base; revisa si todos son necesarios.</p>
      )}
      {plan && (
        <>
          <p>
            Ahorro planificado del mes <Strong>{money(plan.planned)}</Strong> ·{" "}
            <Strong>{formatPercent(plan.plannedPct)}</Strong> de tu ingreso
          </p>
          {plan.combined && (
            <p>
              Topes + metas <Strong>{money(plan.combined.amount)}</Strong> ·{" "}
              <Strong>{formatPercent(plan.combined.pct)}</Strong> de tu ingreso
            </p>
          )}
          {plan.exceedsIncome && (
            <p>
              Topes y ahorro planificado suman más que tu ingreso base; revisa si el plan
              te alcanza.
            </p>
          )}
        </>
      )}
    </div>
  );
}
