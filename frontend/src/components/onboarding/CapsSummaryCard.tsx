"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

import { formatMoney, formatPercent } from "@/lib/format";
import type { CapsSummary } from "@/lib/categoryCaps";

/** How long the figures must stay still before they are announced to screen readers. */
const ANNOUNCE_DELAY_MS = 700;

interface CapsSummaryCardProps {
  summary: CapsSummary;
  income: number | null;
  currency: string;
}

function topesLabel(count: number): string {
  return `${count} ${count === 1 ? "tope" : "topes"}`;
}

/** Summary above the scrolling content: how many topes, their total and (with an
 *  income) the share of it. The text updates instantly; screen readers get it once
 *  typing pauses, not on every key. Over 100% says so in words and icon. */
export function CapsSummaryCard({ summary, income, currency }: CapsSummaryCardProps) {
  const { count, total, pct } = summary;
  const over = pct !== null && pct > 100;
  const money = formatMoney(total, currency);
  const share =
    pct === null ? "" : over ? `superas tu ingreso (${formatPercent(pct)})` : `${formatPercent(pct)} de tu ingreso`;
  const valueText = pct === null ? undefined : share;

  const spoken = `${topesLabel(count)}, ${money}${share ? `, ${share}` : ""}`;
  const [liveText, setLiveText] = useState(spoken);
  useEffect(() => {
    const timer = setTimeout(() => setLiveText(spoken), ANNOUNCE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [spoken]);

  return (
    <div className="shrink-0 rounded-xl border border-line bg-surface px-4 py-3 shadow-card">
      <p className="text-sm font-semibold text-ink">
        {topesLabel(count)} · <span className="tabular-nums">{money}</span>
        {pct !== null && !over && (
          <span className="ml-1 font-medium text-brand-700">{formatPercent(pct)} de tu ingreso</span>
        )}
      </p>
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {liveText}
      </p>
      {over && (
        <p className="mt-1 flex items-center gap-1.5 text-xs font-medium text-amber-700">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          Superas tu ingreso ({formatPercent(pct)})
        </p>
      )}
      {pct !== null && income !== null && (
        <>
          <div
            className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-label="Parte de tu ingreso que ocupan tus topes"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.min(100, Math.round(pct))}
            aria-valuetext={valueText}
          >
            <div
              className={`h-full rounded-full transition-all ${over ? "bg-amber-600" : "bg-brand-600"}`}
              style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs text-muted">
            Tu ingreso base: {formatMoney(income, currency)} al mes
          </p>
        </>
      )}
    </div>
  );
}
