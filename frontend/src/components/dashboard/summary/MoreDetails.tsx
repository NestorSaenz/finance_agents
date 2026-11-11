"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

/** "Más detalles": folded by default; holds what the top of the summary leaves out
 *  but must stay reachable (recurrentes, pagos, split, gastos por categoría). */
export function MoreDetails({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={id}
        className="flex min-h-11 w-full items-center justify-between gap-2 rounded-xl border border-line bg-surface px-4 text-sm font-medium text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
      >
        Más detalles
        <ChevronDown
          className={`h-4 w-4 text-muted transition-transform motion-reduce:transition-none ${
            open ? "rotate-180" : ""
          }`}
          aria-hidden
        />
      </button>
      <div id={id} hidden={!open} className="mt-5 flex flex-col gap-5">
        {open && children}
      </div>
    </div>
  );
}
