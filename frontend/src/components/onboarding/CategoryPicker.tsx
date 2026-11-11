"use client";

import { ChevronDown, Plus } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { canCreate, filterCategories, normalizeCategory } from "@/lib/categoryCaps";
import { categoryLabel } from "@/lib/format";

interface CategoryPickerProps {
  commonCategories: string[];
  moreCategories: string[];
  customCategories: string[];
  selected: string[];
  /** A suggested / existing category was picked. */
  onChoose: (category: string) => void;
  /** A new category name (already normalized) was created. */
  onCreate: (category: string) => void;
}

/** "Agregar más": search box, chips with what is still missing, and "Crear «x»". */
export function CategoryPicker({
  commonCategories,
  moreCategories,
  customCategories,
  selected,
  onChoose,
  onCreate,
}: CategoryPickerProps) {
  const [query, setQuery] = useState("");
  const [showMore, setShowMore] = useState(false);
  const id = useId();
  const results = useRef<HTMLDivElement>(null);

  const all = [...commonCategories, ...moreCategories, ...customCategories];
  const searching = query.trim() !== "";
  const pool = searching
    ? all
    : [...commonCategories, ...(showMore ? moreCategories : []), ...customCategories];
  const chips = filterCategories(query, pool, selected);
  const creatable = canCreate(query, all);
  const first = chips[0];

  // Keep the matches and "Crear" inside the visible part of the scroll area.
  useEffect(() => {
    if (searching) results.current?.scrollIntoView?.({ block: "nearest" });
  }, [query, searching]);

  function choose(category: string) {
    setQuery("");
    onChoose(category);
  }

  function create() {
    const category = normalizeCategory(query);
    if (!category) return;
    setQuery("");
    onCreate(category);
  }

  return (
    <section className="mt-6 pb-2" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="text-sm font-semibold text-ink">
        Agregar más
      </h2>
      <label htmlFor={`${id}-search`} className="sr-only">
        Busca o escribe una categoría nueva
      </label>
      <input
        id={`${id}-search`}
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Enter") return;
          e.preventDefault();
          // A visible match wins over creating a near-duplicate ("rest" -> Restaurantes);
          // "Crear" with partial matches around is the explicit button.
          if (first) choose(first);
          else if (creatable) create();
        }}
        placeholder="Busca o escribe una categoría nueva"
        autoComplete="off"
        className="mt-2 min-h-11 w-full rounded-xl border border-line bg-white px-3.5 text-sm text-ink placeholder:text-slate-500 focus:border-brand-500"
      />

      <div ref={results} id={`${id}-chips`} className="mt-3 flex flex-wrap gap-2">
        {chips.map((category) => (
          <button
            key={category}
            type="button"
            onClick={() => choose(category)}
            className="inline-flex min-h-11 items-center gap-1 rounded-full border border-line bg-white px-3.5 text-sm font-medium text-ink transition-colors hover:border-brand-400"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden />
            {categoryLabel(category)}
          </button>
        ))}
        {creatable && (
          <button
            type="button"
            onClick={create}
            className="inline-flex min-h-11 items-center gap-1 rounded-full border border-dashed border-brand-600 bg-brand-50 px-3.5 text-sm font-medium text-brand-700"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden />
            Crear «{normalizeCategory(query)}»
          </button>
        )}
        {!searching && moreCategories.length > 0 && (
          <button
            type="button"
            onClick={() => setShowMore((v) => !v)}
            aria-expanded={showMore}
            aria-controls={`${id}-chips`}
            className="inline-flex min-h-11 items-center gap-1 rounded-full border border-dashed border-line px-3.5 text-sm font-medium text-muted hover:text-ink"
          >
            {showMore ? "Menos categorías" : "Más categorías"}
            <ChevronDown
              className={`h-4 w-4 transition-transform motion-reduce:transition-none ${
                showMore ? "rotate-180" : ""
              }`}
              aria-hidden
            />
          </button>
        )}
      </div>
      {searching && chips.length === 0 && !creatable && (
        <p className="mt-2 text-sm text-muted">Esa categoría ya está en tus topes.</p>
      )}
      {!searching && (
        <p className="mt-3 text-xs text-muted">Lo que elijas pasa arriba, a «Tus topes».</p>
      )}
    </section>
  );
}
