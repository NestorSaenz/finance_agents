"use client";

import { formatMoney } from "@/lib/format";
import type { Goal } from "@/lib/types";

/** Savings goals with a progress bar (current vs target). */
export function GoalProgress({ goals }: { goals: Goal[] }) {
  // Show goals still in play (active/completed), most-funded first.
  const visible = goals
    .filter((g) => g.status === "active" || g.status === "completed")
    .sort((a, b) => Number(b.current_amount) - Number(a.current_amount));

  if (visible.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      {visible.map((g) => {
        const current = Number(g.current_amount);
        const target = Number(g.target_amount);
        const pct = target > 0 ? (current / target) * 100 : 0;
        const done = pct >= 100;
        return (
          <div key={g.id}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="text-ink">{g.name}</span>
              <span className={done ? "text-positive" : "text-muted"}>
                {formatMoney(current)}{" "}
                <span className="text-muted">/ {formatMoney(target)}</span>
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-all ${
                  done ? "bg-positive" : "bg-brand-600"
                }`}
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
