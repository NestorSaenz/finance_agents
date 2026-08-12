"use client";

import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/Button";

export interface RecurringDraft {
  id: string; // stable key so removing a row doesn't remap input state
  description: string;
  amount: string;
  transactionType: "income" | "expense";
  day: string;
}

export function newRecurring(): RecurringDraft {
  return {
    id: crypto.randomUUID(),
    description: "",
    amount: "",
    transactionType: "expense",
    day: "",
  };
}

const INPUT =
  "min-h-11 rounded-lg border border-line px-2.5 text-sm text-ink placeholder:text-slate-400 focus:border-brand-500";

interface RecurringStepProps {
  recurring: RecurringDraft[];
  submitting: boolean;
  error: string | null;
  onUpdate: (
    index: number,
    field: keyof Omit<RecurringDraft, "id">,
    value: string,
  ) => void;
  onRemove: (index: number) => void;
  onAdd: () => void;
  onBack: () => void;
  onSkip: () => void;
  onFinish: () => void;
}

/** Onboarding step 4: optional fixed monthly movements (salary, rent, subs…). */
export function RecurringStep({
  recurring,
  submitting,
  error,
  onUpdate,
  onRemove,
  onAdd,
  onBack,
  onSkip,
  onFinish,
}: RecurringStepProps) {
  return (
    <>
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Tus movimientos fijos</h1>
        <p className="mt-1 text-sm text-muted">
          ¿Tienes ingresos o gastos que se repiten cada mes? Sueldo, arriendo,
          suscripciones… los registramos una vez y aparecen solos. Todo es opcional.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {recurring.map((row, index) => (
          <div key={row.id} className="rounded-xl border border-line bg-white p-3">
            <div className="mb-2 flex items-center gap-2">
              <input
                type="text"
                placeholder="Descripción (ej. Sueldo)"
                value={row.description}
                onChange={(e) => onUpdate(index, "description", e.target.value)}
                aria-label={`Descripción del movimiento ${index + 1}`}
                className={`flex-1 px-3 ${INPUT}`}
              />
              <button
                type="button"
                onClick={() => onRemove(index)}
                aria-label={`Quitar movimiento ${index + 1}`}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-slate-100 hover:text-negative"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>

            {/* Ingreso / gasto toggle */}
            <div
              className="mb-2 flex gap-1"
              role="group"
              aria-label={`Tipo del movimiento ${index + 1}`}
            >
              <button
                type="button"
                aria-pressed={row.transactionType === "income"}
                onClick={() => onUpdate(index, "transactionType", "income")}
                className={`min-h-11 flex-1 rounded-lg px-3 text-sm font-medium transition-colors ${
                  row.transactionType === "income"
                    ? "bg-positive text-white"
                    : "bg-slate-100 text-muted hover:text-ink"
                }`}
              >
                Ingreso
              </button>
              <button
                type="button"
                aria-pressed={row.transactionType === "expense"}
                onClick={() => onUpdate(index, "transactionType", "expense")}
                className={`min-h-11 flex-1 rounded-lg px-3 text-sm font-medium transition-colors ${
                  row.transactionType === "expense"
                    ? "bg-ink text-white"
                    : "bg-slate-100 text-muted hover:text-ink"
                }`}
              >
                Gasto
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                inputMode="decimal"
                min={0}
                placeholder="Monto"
                value={row.amount}
                onChange={(e) => onUpdate(index, "amount", e.target.value)}
                aria-label={`Monto del movimiento ${index + 1}`}
                className={INPUT}
              />
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={31}
                placeholder="Día del mes"
                value={row.day}
                onChange={(e) => onUpdate(index, "day", e.target.value)}
                aria-label={`Día del mes del movimiento ${index + 1}`}
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
          Agregar movimiento
        </button>
      </div>

      {error && <p className="mt-4 text-sm text-negative">{error}</p>}

      <div className="mt-6 flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack} disabled={submitting}>
          Atrás
        </Button>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={onSkip} disabled={submitting}>
            Omitir
          </Button>
          <Button onClick={onFinish} loading={submitting} className="min-w-28">
            Finalizar
          </Button>
        </div>
      </div>
    </>
  );
}
