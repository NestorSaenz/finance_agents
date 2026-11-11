"use client";

import { Info } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

interface InfoDisclosureProps {
  /** What the note explains ("Balance"): the button is named "Qué significa Balance". */
  label: string;
  children: ReactNode;
}

/** A 44×44 "i" button that reveals a long explanatory note BELOW it (not a tooltip).
 *  Use only for definitions; notes that change how a figure reads stay visible. */
export function InfoDisclosure({ label, children }: InfoDisclosureProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={id}
        aria-label={`Qué significa ${label}`}
        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-slate-100 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
      >
        <Info size={18} aria-hidden />
      </button>
      <div id={id} hidden={!open} className="basis-full text-xs text-muted">
        {open && children}
      </div>
    </>
  );
}
