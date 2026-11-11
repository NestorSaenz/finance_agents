"use client";

import { useMoney } from "@/context/CurrencyContext";

export function StatCard({
  label,
  value,
  tone,
  details = [],
}: {
  label: string;
  value: string | number;
  tone: "positive" | "negative";
  /** Muted breakdown / notes shown under the amount. */
  details?: string[];
}) {
  const money = useMoney();
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p
        className={`mt-1 text-lg font-semibold ${
          tone === "positive" ? "text-positive" : "text-negative"
        }`}
      >
        {money(value)}
      </p>
      {details.map((d) => (
        <p key={d} className="mt-1 break-words text-xs text-muted">
          {d}
        </p>
      ))}
    </div>
  );
}
