"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";

import { formatMoney } from "@/lib/format";
import { monthLabel, monthSummaries } from "@/lib/goalPlans";
import type { GoalMonthLine } from "@/lib/types";

interface GoalPlanHistoryProps {
  lines: GoalMonthLine[];
  /** The one currency summarised (currencies are never mixed). */
  currency: string;
  /** Currency the amounts are shown in (the profile's); defaults to `currency`. */
  displayCurrency?: string;
  /** "YYYY-MM" marked as the viewed month; null with "Todo" (none marked). */
  selectedMonth: string | null;
  /** Last month of the window (the chosen month, or the current one). */
  endMonth: string;
  /** Called with "YYYY-MM" when the user taps a month. */
  onSelectMonth: (month: string) => void;
}

/** ONE accordion with a row per month: plan vs saved, and how many goals met it.
 *  Tapping a month switches the whole panel to it. */
export function GoalPlanHistory({
  lines,
  currency,
  displayCurrency = currency,
  selectedMonth,
  endMonth,
  onSelectMonth,
}: GoalPlanHistoryProps) {
  const [open, setOpen] = useState(false);
  const regionId = useId();
  const months = monthSummaries(lines, currency, endMonth);
  if (months.length === 0) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={open ? regionId : undefined}
        className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-md text-left text-sm font-medium text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
      >
        Historial de planes (últimos 5 meses)
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted transition-transform motion-reduce:transition-none ${
            open ? "rotate-180" : ""
          }`}
          aria-hidden
        />
      </button>

      {open && (
        <div id={regionId}>
          <p className="mb-1 text-xs text-muted">Toca un mes para verlo</p>
          <ul className="flex flex-col gap-1">
            {[...months].reverse().map((m) => {
              const current = m.month === selectedMonth;
              const fill = m.planned > 0 ? Math.min(100, (m.saved / m.planned) * 100) : 0;
              return (
                <li key={m.month}>
                  <button
                    type="button"
                    onClick={() => onSelectMonth(m.month)}
                    aria-current={current ? "date" : undefined}
                    className={`min-h-[44px] w-full rounded-lg px-2 py-1.5 text-left text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
                      current ? "bg-brand-50 ring-1 ring-brand-400" : "hover:bg-slate-50"
                    }`}
                  >
                    <span className="text-ink">
                      {monthLabel(m.month)} · aportado {formatMoney(m.saved, displayCurrency)} de{" "}
                      {formatMoney(m.planned, displayCurrency)} · {m.met}/{m.total} cumplidas
                    </span>
                    <span className="mt-1 block h-1 w-full overflow-hidden rounded-full bg-slate-100">
                      <span
                        className={`block h-full rounded-full ${
                          m.met === m.total ? "bg-positive" : "bg-brand-600"
                        }`}
                        style={{ width: `${fill}%` }}
                      />
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
