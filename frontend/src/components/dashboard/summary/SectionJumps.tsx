"use client";

export interface JumpSection {
  /** id of the wrapper element of the section (inside the scrolling panel). */
  id: string;
  /** Short text on the chip. */
  label: string;
  /** Full name for screen readers (defaults to `label`). */
  fullLabel?: string;
}

/** Move to a section INSIDE the panel's scroll container and put focus on its
 *  heading (or the section itself). Motion is skipped with prefers-reduced-motion. */
export function jumpToSection(id: string): void {
  const target = document.getElementById(id);
  if (!target) return;
  const reduced =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // scrollIntoView scrolls the nearest scrollable ancestor: the panel, not the window.
  target.scrollIntoView?.({ block: "start", behavior: reduced ? "auto" : "smooth" });
  const heading = target.querySelector<HTMLElement>("h2, h3") ?? target;
  if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
  heading.classList.add("focus:outline-none");
  heading.focus({ preventScroll: true });
}

/** Chips that jump to the sections that exist (one chip per shown section). */
export function SectionJumps({ sections }: { sections: JumpSection[] }) {
  if (sections.length === 0) return null;
  return (
    <nav aria-label="Ir a una sección" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      {sections.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => jumpToSection(s.id)}
          aria-label={s.fullLabel ?? s.label}
          className="inline-flex min-h-11 shrink-0 items-center rounded-full border border-line bg-surface px-3 text-sm font-medium text-ink transition-colors hover:border-brand-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
        >
          {s.label}
        </button>
      ))}
    </nav>
  );
}
