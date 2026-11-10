"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";

import { formatMoney } from "@/lib/format";
import { monthLabel, monthState } from "@/lib/goalPlans";
import type { GoalMonthLine } from "@/lib/types";

interface GoalMonthHistoryProps {
  goalName: string;
  /** This goal's rows, oldest first, ending at the chosen month. */
  lines: GoalMonthLine[];
  /** "YYYY-MM" highlighted as the chosen month. */
  selectedMonth: string;
}

/** Per-goal "Ver mes a mes" accordion: plan vs contributed for each month. */
export function GoalMonthHistory({ goalName, lines, selectedMonth }: GoalMonthHistoryProps) {
  const [open, setOpen] = useState(false);
  const regionId = useId();
  if (lines.length === 0) return null;

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`Ver mes a mes de ${goalName}`}
        aria-controls={open ? regionId : undefined}
        className="inline-flex min-h-[44px] items-center gap-1 rounded-md py-2.5 text-xs font-medium text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
      >
        Ver mes a mes
        <ChevronDown
          className={`h-4 w-4 transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>

      {open && (
        <ul id={regionId} className="mt-1 flex flex-col gap-1">
          {lines.map((l) => {
            const state = monthState(l);
            const withdrawn = Number(l.withdrawn);
            const current = l.month === selectedMonth;
            return (
              <li
                key={l.month}
                aria-current={current ? "date" : undefined}
                className={`rounded-lg px-2 py-1.5 text-xs ${
                  current ? "bg-brand-50 ring-1 ring-brand-400" : ""
                }`}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                  <span className="text-ink">
                    {monthLabel(l.month)} ·{" "}
                    <span className="tabular-nums">
                      {formatMoney(l.saved, l.currency)}
                      {l.planned !== null && ` / ${formatMoney(l.planned, l.currency)}`}
                    </span>
                  </span>
                  <span className="text-muted">
                    {state.kind === "cumplido" && "✓"}
                    {state.kind === "faltan" && `faltan ${formatMoney(state.missing, l.currency)}`}
                    {state.kind === "sin_plan" && "sin plan"}
                  </span>
                </div>
                {state.kind !== "sin_plan" && (
                  <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className={`h-full rounded-full ${
                        state.kind === "cumplido" ? "bg-positive" : "bg-brand-600"
                      }`}
                      style={{ width: `${state.fill}%` }}
                    />
                  </div>
                )}
                {withdrawn > 0 && (
                  <p className="mt-0.5 text-[11px] text-muted">
                    retiraste {formatMoney(withdrawn, l.currency)}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
