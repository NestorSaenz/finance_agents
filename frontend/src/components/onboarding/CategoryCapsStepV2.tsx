"use client";

import { useEffect, useRef, useState } from "react";

import { capsSummary } from "@/lib/categoryCaps";

import { CapsSummaryCard } from "./CapsSummaryCard";
import { CategoryPicker } from "./CategoryPicker";
import { COLLAPSED_ROWS, SelectedCapsList } from "./SelectedCapsList";
import { StepActions } from "./StepActions";

interface CategoryCapsStepV2Props {
  /** Suggested categories, most common first. */
  commonCategories: string[];
  /** Less common suggestions, folded under "Más categorías". */
  moreCategories: string[];
  /** Categories the user created (shown as "tuya"). */
  customCategories: string[];
  /** Chosen categories, in the order they were chosen. */
  selected: string[];
  /** Amount typed per category, as plain digits. */
  caps: Record<string, string>;
  /** Monthly income typed in step 1 (null when none). */
  income: number | null;
  currency: string;
  submitting: boolean;
  onToggle: (category: string) => void;
  onAddCustom: (category: string) => void;
  onCapChange: (category: string, value: string) => void;
  onBack: () => void;
  onContinue: () => void;
}

/**
 * Onboarding step 2 (redesign). Three stacked regions inside the wizard card:
 * the summary on top, the scrolling content (title, chosen topes, picker) and the
 * action footer below it. Only the middle scrolls, so nothing sits under the footer.
 * Needs a flex-column parent with a bounded height (the wizard card provides it).
 */
export function CategoryCapsStepV2({
  commonCategories,
  moreCategories,
  customCategories,
  selected,
  caps,
  income,
  currency,
  submitting,
  onToggle,
  onAddCustom,
  onCapChange,
  onBack,
  onContinue,
}: CategoryCapsStepV2Props) {
  const [expanded, setExpanded] = useState(false);
  const [focusRequest, setFocusRequest] = useState<string | null>(null);
  const content = useRef<HTMLDivElement>(null);
  const summary = capsSummary(selected, caps, income);

  // After picking / creating a category its row exists: move focus to its amount
  // (an explicit user action; the chip they pressed has just disappeared).
  useEffect(() => {
    if (!focusRequest || !selected.includes(focusRequest)) return;
    const fields = content.current?.querySelectorAll<HTMLInputElement>("input[data-cap-input]");
    const field = Array.from(fields ?? []).find((el) => el.dataset.capInput === focusRequest);
    field?.focus();
    field?.scrollIntoView?.({ block: "nearest" });
    setFocusRequest(null);
  }, [focusRequest, selected]);

  /** Open the list when it is long, so the new row is visible, and ask for focus. */
  function afterAdd(category: string) {
    if (selected.length >= COLLAPSED_ROWS) setExpanded(true);
    setFocusRequest(category);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <CapsSummaryCard summary={summary} income={income} currency={currency} />

      <div ref={content} className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
        <div className="mb-1">
          <h1 className="text-xl font-semibold text-ink">Topes por categoría</h1>
          <p className="mt-1 text-sm text-muted">
            Un límite mensual por categoría. Te avisamos cuando te acerques. Todo es opcional.
          </p>
        </div>

        <SelectedCapsList
          selected={selected}
          caps={caps}
          customCategories={customCategories}
          income={income}
          expanded={expanded}
          onToggleExpanded={() => setExpanded((v) => !v)}
          onCapChange={onCapChange}
          onRemove={onToggle}
        />

        <CategoryPicker
          commonCategories={commonCategories}
          moreCategories={moreCategories}
          customCategories={customCategories}
          selected={selected}
          onChoose={(category) => {
            onToggle(category);
            afterAdd(category);
          }}
          onCreate={(category) => {
            onAddCustom(category);
            afterAdd(category);
          }}
        />
      </div>

      <StepActions submitting={submitting} onBack={onBack} onContinue={onContinue} />
    </div>
  );
}
