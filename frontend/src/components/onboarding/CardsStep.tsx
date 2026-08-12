"use client";

import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/Button";

export interface CardDraft {
  id: string; // stable key so removing a row doesn't remap input state
  name: string;
  limit: string;
  cutoff: string;
  payment: string;
}

export function newCard(): CardDraft {
  return { id: crypto.randomUUID(), name: "", limit: "", cutoff: "", payment: "" };
}

const INPUT =
  "min-h-11 rounded-lg border border-line px-2.5 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500";

interface CardsStepProps {
  cards: CardDraft[];
  onUpdate: (index: number, field: keyof CardDraft, value: string) => void;
  onRemove: (index: number) => void;
  onAdd: () => void;
  onBack: () => void;
  onContinue: () => void;
}

/** Onboarding step 3: register credit cards (name only, no sensitive data). */
export function CardsStep({
  cards,
  onUpdate,
  onRemove,
  onAdd,
  onBack,
  onContinue,
}: CardsStepProps) {
  return (
    <>
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Tarjetas de crédito</h1>
        <p className="mt-1 text-sm text-muted">
          Agrega tus tarjetas para llevar el control del cupo y el ciclo. Solo el
          nombre, sin números ni datos sensibles. Todo es opcional.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {cards.map((card, index) => (
          <div key={card.id} className="rounded-xl border border-line bg-white p-3">
            <div className="mb-2 flex items-center gap-2">
              <input
                type="text"
                placeholder="Nombre (ej. Visa BBVA)"
                value={card.name}
                onChange={(e) => onUpdate(index, "name", e.target.value)}
                aria-label={`Nombre de la tarjeta ${index + 1}`}
                className={`flex-1 px-3 ${INPUT}`}
              />
              <button
                type="button"
                onClick={() => onRemove(index)}
                aria-label={`Quitar tarjeta ${index + 1}`}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-slate-100 hover:text-negative"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                inputMode="decimal"
                min={0}
                placeholder="Cupo"
                value={card.limit}
                onChange={(e) => onUpdate(index, "limit", e.target.value)}
                aria-label={`Cupo de la tarjeta ${index + 1}`}
                className={INPUT}
              />
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={31}
                placeholder="Corte"
                value={card.cutoff}
                onChange={(e) => onUpdate(index, "cutoff", e.target.value)}
                aria-label={`Día de corte de la tarjeta ${index + 1}`}
                className={INPUT}
              />
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={31}
                placeholder="Pago"
                value={card.payment}
                onChange={(e) => onUpdate(index, "payment", e.target.value)}
                aria-label={`Día de pago de la tarjeta ${index + 1}`}
                className={INPUT}
              />
            </div>
          </div>
        ))}

        <button
          type="button"
          onClick={onAdd}
          className="inline-flex min-h-11 items-center justify-center gap-1 rounded-xl border border-dashed border-line py-2.5 text-sm font-medium text-muted hover:text-ink"
        >
          <Plus className="h-4 w-4" aria-hidden />
          Agregar tarjeta
        </button>
      </div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack}>
          Atrás
        </Button>
        <Button onClick={onContinue} className="min-w-28">
          Continuar
        </Button>
      </div>
    </>
  );
}
