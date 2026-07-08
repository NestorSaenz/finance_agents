"use client";

import { Sparkles } from "lucide-react";

import { formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

interface WelcomeStepProps {
  name: string;
  income: string;
  savings: string;
  incomeValid: boolean;
  savingsValid: boolean;
  savingsPreview: number | null;
  submitting: boolean;
  onNameChange: (v: string) => void;
  onIncomeChange: (v: string) => void;
  onSavingsChange: (v: string) => void;
  onSkip: () => void;
  onContinue: () => void;
}

/** Onboarding step 1: who the user is + income + savings goal. */
export function WelcomeStep({
  name,
  income,
  savings,
  incomeValid,
  savingsValid,
  savingsPreview,
  submitting,
  onNameChange,
  onIncomeChange,
  onSavingsChange,
  onSkip,
  onContinue,
}: WelcomeStepProps) {
  return (
    <>
      <div className="mb-5">
        <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-positive text-white">
          <Sparkles className="h-5 w-5" aria-hidden />
        </div>
        <h1 className="text-xl font-semibold text-ink">¡Te damos la bienvenida!</h1>
        <p className="mt-1 text-sm text-muted">
          Cuéntanos un poco de ti para personalizar tu experiencia. Puedes omitir este
          paso y hacerlo más tarde.
        </p>
      </div>

      <div className="mb-4">
        <Input
          label="¿Cómo te llamas? (opcional)"
          type="text"
          autoComplete="given-name"
          placeholder="Ej. Néstor"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
        />
      </div>

      <Input
        label="Ingreso mensual (opcional)"
        type="number"
        inputMode="decimal"
        min={0}
        placeholder="Ej. 30000"
        value={income}
        onChange={(e) => onIncomeChange(e.target.value)}
        error={!incomeValid ? "Ingresa un monto válido." : undefined}
      />
      <p className="mt-1.5 text-xs text-muted">
        ¿Tu ingreso varía cada mes? Déjalo vacío o pon un promedio — Safi usa tus
        ingresos reales registrados en cada período.
      </p>

      <div className="mt-4">
        <Input
          label="Meta de ahorro mensual (opcional)"
          type="number"
          inputMode="decimal"
          min={0}
          max={100}
          placeholder="Ej. 20"
          value={savings}
          onChange={(e) => onSavingsChange(e.target.value)}
          error={!savingsValid ? "Usa un porcentaje entre 0 y 100." : undefined}
          className="pr-8"
        />
        <p className="mt-1.5 text-xs text-muted">
          Porcentaje de tus ingresos que quieres apartar.
          {savingsPreview !== null && (
            <span className="font-medium text-positive"> ≈ {formatMoney(savingsPreview)}/mes.</span>
          )}
        </p>
      </div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onSkip} disabled={submitting}>
          Omitir
        </Button>
        <Button
          onClick={onContinue}
          disabled={!incomeValid || !savingsValid}
          className="min-w-28"
        >
          Continuar
        </Button>
      </div>
    </>
  );
}
