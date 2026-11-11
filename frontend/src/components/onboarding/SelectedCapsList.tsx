"use client";

import { ChevronDown, X } from "lucide-react";
import { useId } from "react";

import { capPct } from "@/lib/categoryCaps";
import { categoryLabel, formatPercent } from "@/lib/format";
import { parseAmountInput } from "@/lib/moneyInput";

import { AmountInput } from "./AmountInput";

/** Rows shown before "Ver los N topes". */
export const COLLAPSED_ROWS = 5;

interface SelectedCapsListProps {
  selected: string[];
  caps: Record<string, string>;
  customCategories: string[];
  income: number | null;
  expanded: boolean;
  onToggleExpanded: () => void;
  onCapChange: (category: string, digits: string) => void;
  onRemove: (category: string) => void;
}

/** "Tus topes": one row per chosen category (name, share, amount, remove), the
 *  first 5 and a toggle for the rest. The visible share is short ("10,5%"); the
 *  full sentence is read by screen readers through aria-describedby. */
export function SelectedCapsList({
  selected,
  caps,
  customCategories,
  income,
  expanded,
  onToggleExpanded,
  onCapChange,
  onRemove,
}: SelectedCapsListProps) {
  const listId = useId();
  const rows = expanded ? selected : selected.slice(0, COLLAPSED_ROWS);

  return (
    <section className="mt-5" aria-labelledby={`${listId}-title`}>
      <h2 id={`${listId}-title`} className="text-sm font-semibold text-ink">
        Tus topes
      </h2>
      {selected.length === 0 ? (
        <p className="mt-2 text-sm text-muted">Aún no elegiste ninguno. Agrega categorías abajo.</p>
      ) : (
        <ul id={listId} className="mt-2 flex flex-col gap-3">
          {rows.map((category) => {
            const label = categoryLabel(category);
            const share = capPct(parseAmountInput(caps[category] ?? ""), income);
            const hasShare = share !== null && share > 0;
            const own = customCategories.includes(category);
            const descId = `${listId}-${category}-desc`;
            return (
              <li key={category} className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm text-ink">{label}</p>
                  {(hasShare || own) && (
                    <>
                      <p className="whitespace-nowrap text-xs text-muted" aria-hidden>
                        {hasShare && formatPercent(share)}
                        {hasShare && own && " · "}
                        {own && "tuya"}
                      </p>
                      <span id={descId} className="sr-only">
                        {hasShare && `${formatPercent(share)} de tu ingreso`}
                        {hasShare && own && ", "}
                        {own && "categoría propia"}
                      </span>
                    </>
                  )}
                </div>
                <AmountInput
                  value={caps[category] ?? ""}
                  onValueChange={(digits) => onCapChange(category, digits)}
                  placeholder="Monto"
                  aria-label={`Tope mensual para ${label}`}
                  aria-describedby={hasShare || own ? descId : undefined}
                  data-cap-input={category}
                  className="min-h-11 w-28 shrink-0 rounded-xl border border-line bg-white px-3 text-right text-sm tabular-nums text-ink placeholder:text-slate-500 focus:border-brand-500"
                />
                <button
                  type="button"
                  onClick={() => onRemove(category)}
                  aria-label={`Quitar ${label}`}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-slate-100 hover:text-negative"
                >
                  <X className="h-4 w-4" aria-hidden />
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {selected.length > COLLAPSED_ROWS && (
        <button
          type="button"
          onClick={onToggleExpanded}
          aria-expanded={expanded}
          aria-controls={listId}
          className="mt-1 inline-flex min-h-11 items-center gap-1 rounded-md text-sm font-medium text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
        >
          {expanded ? "Ver menos" : `Ver los ${selected.length} topes`}
          <ChevronDown
            className={`h-4 w-4 transition-transform motion-reduce:transition-none ${
              expanded ? "rotate-180" : ""
            }`}
            aria-hidden
          />
        </button>
      )}
    </section>
  );
}
