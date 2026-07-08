import { LineChart } from "lucide-react";

const SUGGESTIONS = [
  "Gasté 200.000 en el supermercado",
  "¿En qué gasto más este mes?",
  "Crea un presupuesto de comida de 600.000",
  "Quiero ahorrar 2.000.000 para un viaje",
];

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-10 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-positive text-white shadow-pop">
        <LineChart className="h-7 w-7" aria-hidden />
      </span>
      <h1 className="mt-5 text-xl font-semibold text-ink">¿En qué te ayudo hoy?</h1>
      <p className="mt-1.5 max-w-sm text-sm text-muted">
        Registra y consulta gastos, controla presupuestos y planifica tu ahorro, conversando en
        lenguaje natural.
      </p>

      <div className="mt-7 grid w-full max-w-lg grid-cols-1 gap-2.5 sm:grid-cols-2">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            onClick={() => onPick(text)}
            className="rounded-xl border border-line bg-surface px-4 py-3 text-left text-sm text-ink shadow-card transition-colors hover:border-brand-300 hover:bg-brand-50"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
