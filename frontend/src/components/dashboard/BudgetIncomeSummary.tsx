"use client";

import { useMoney } from "@/context/CurrencyContext";
import type { BudgetIncomeShare } from "@/lib/budgets";
import { formatPercent } from "@/lib/format";

function Strong({ children }: { children: React.ReactNode }) {
  return <span className="font-semibold tabular-nums text-ink">{children}</span>;
}

/** What share of the base income the topes occupy: the monthly category total,
 *  the overall tope apart, and a calm note when they exceed the income. Renders
 *  nothing when there is no tope to report. */
export function BudgetIncomeSummary({ share }: { share: BudgetIncomeShare }) {
  const money = useMoney();
  if (share.categoryTotal <= 0 && !share.overall) return null;

  return (
    <div className="flex flex-col gap-0.5 text-xs text-muted">
      {share.categoryTotal > 0 && (
        <p>
          Tus topes suman <Strong>{money(share.categoryTotal)}</Strong> ·{" "}
          <Strong>{formatPercent(share.totalPct)}</Strong> de tu ingreso
        </p>
      )}
      {share.overall && (
        <p>
          Tope general <Strong>{money(share.overall.amount)}</Strong> ·{" "}
          <Strong>{formatPercent(share.overall.pct)}</Strong> de tu ingreso (aparte del
          total)
        </p>
      )}
      {share.totalPct > 100 && (
        <p>Tus topes suman más que tu ingreso base; revisa si todos son necesarios.</p>
      )}
    </div>
  );
}
