"use client";

import { Button } from "@/components/ui/Button";

interface StepActionsProps {
  submitting: boolean;
  onBack: () => void;
  onContinue: () => void;
}

/** Back / Continue footer, pinned below the scrolling content (never over it).
 *  It bleeds to the card edges and respects the device safe area. */
export function StepActions({ submitting, onBack, onContinue }: StepActionsProps) {
  return (
    <div
      className="-mx-6 -mb-6 shrink-0 border-t border-line bg-surface px-6 pt-3 sm:-mx-8 sm:-mb-8 sm:px-8"
      style={{ paddingBottom: "calc(0.75rem + env(safe-area-inset-bottom))" }}
    >
      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack} disabled={submitting} className="min-h-12">
          Atrás
        </Button>
        <Button onClick={onContinue} className="min-h-12 min-w-28">
          Continuar
        </Button>
      </div>
    </div>
  );
}
