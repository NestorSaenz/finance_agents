"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";

import { categoryLabel } from "@/lib/format";
import { Button } from "@/components/ui/Button";

interface CategoryCapsStepProps {
  chipCategories: string[];
  selected: string[];
  caps: Record<string, string>;
  showMore: boolean;
  submitting: boolean;
  onToggle: (category: string) => void;
  onAddCustom: (category: string) => void;
  onCapChange: (category: string, value: string) => void;
  onShowMore: () => void;
  onBack: () => void;
  onContinue: () => void;
}

/** Onboarding step 2: optional monthly spending caps per category. */
export function CategoryCapsStep({
  chipCategories,
  selected,
  caps,
  showMore,
  submitting,
  onToggle,
  onAddCustom,
  onCapChange,
  onShowMore,
  onBack,
  onContinue,
}: CategoryCapsStepProps) {
  const [custom, setCustom] = useState("");

  function submitCustom() {
    onAddCustom(custom);
    setCustom("");
  }

  return (
    <>
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Topes por categoría</h1>
        <p className="mt-1 text-sm text-muted">
          Elige las categorías en las que quieras un límite mensual y define su monto.
          Te avisaremos cuando te acerques. Todo es opcional.
        </p>
      </div>

      {/* Category picker: tap a chip to add/remove it. */}
      <div className="flex flex-wrap gap-2">
        {chipCategories.map((category) => {
          const active = selected.includes(category);
          return (
            <button
              key={category}
              type="button"
              onClick={() => onToggle(category)}
              aria-pressed={active}
              className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                active
                  ? "border-brand-600 bg-brand-600 text-white"
                  : "border-line bg-white text-muted hover:border-brand-400 hover:text-ink"
              }`}
            >
              {categoryLabel(category)}
            </button>
          );
        })}
        {!showMore && (
          <button
            type="button"
            onClick={onShowMore}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-line px-3 py-1.5 text-sm font-medium text-muted hover:text-ink"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden />
            Ver más
          </button>
        )}
      </div>

      {/* Add your own category (beyond the suggested ones). */}
      <div className="mt-3 flex items-center gap-2">
        <input
          type="text"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submitCustom();
            }
          }}
          placeholder="Otra categoría (ej. jardinería)"
          aria-label="Agregar una categoría propia"
          className="min-h-11 flex-1 rounded-xl border border-line bg-white px-3.5 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500"
        />
        <Button
          variant="ghost"
          onClick={submitCustom}
          disabled={custom.trim() === ""}
          className="min-h-11 shrink-0"
        >
          Agregar
        </Button>
      </div>

      {/* Amount inputs for the selected categories. */}
      {selected.length > 0 && (
        <div className="mt-5 flex flex-col gap-3">
          {selected.map((category) => (
            <div key={category} className="flex items-center gap-3">
              <span className="w-32 shrink-0 text-sm text-ink">
                {categoryLabel(category)}
              </span>
              <input
                type="number"
                inputMode="decimal"
                min={0}
                autoFocus
                placeholder="Monto mensual"
                value={caps[category] ?? ""}
                onChange={(e) => onCapChange(category, e.target.value)}
                aria-label={`Tope mensual para ${categoryLabel(category)}`}
                className="min-h-11 flex-1 rounded-xl border border-line bg-white px-3.5 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500"
              />
              <button
                type="button"
                onClick={() => onToggle(category)}
                aria-label={`Quitar ${categoryLabel(category)}`}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-slate-100 hover:text-negative"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-6 flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack} disabled={submitting}>
          Atrás
        </Button>
        <Button onClick={onContinue} className="min-w-28">
          Continuar
        </Button>
      </div>
    </>
  );
}
