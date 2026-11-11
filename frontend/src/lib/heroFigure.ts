import { formatPercent, MONTHS_ES } from "@/lib/format";
import type { SummaryFigures } from "@/lib/summary";


/** "2026-11" -> "noviembre" ("noviembre 2025" when it is not the year of `now`). */
export function monthName(month: string, now: Date = new Date()): string {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month);
  if (!match) return month;
  const name = MONTHS_ES[Number(match[2]) - 1] ?? month;
  return Number(match[1]) === now.getFullYear() ? name : `${name} ${match[1]}`;
}

export type HeroKind = "caja" | "excedente" | "gastos";

/** The "consumed" bar under the headline (only with an income). */
export interface HeroBar {
  /** spent / income, one decimal (can exceed 100). */
  pct: number;
  /** Width of the fill, 0–100. */
  fill: number;
  over: boolean;
  /** "Consumido 64,5% de tu ingreso" / "Gastaste más que tu ingreso". */
  text: string;
  /** For aria-valuetext: the same sentence, spoken. */
  valueText: string;
  spent: number;
  income: number;
}

export interface HeroFigureData {
  kind: HeroKind;
  /** Eyebrow, e.g. "Tu mes · noviembre" or "De toda tu historia" (caller uppercases). */
  label: string;
  value: number;
  /** By sign. No colors here. */
  tone: "positive" | "negative";
  subtitle: string;
  /** null without an income, and for "todo". */
  bar: HeroBar | null;
  /** Always-visible notes that change how the figure reads. */
  notes: string[];
}

export interface HeroContext {
  period: string;
  /** Backend accumulated surplus (the value SurplusCard shows). */
  accumulatedSurplus: number;
  /** Money formatter in the profile currency. */
  money: (value: number) => string;
  /** Clock for the month name; defaults to the real one. */
  now?: Date;
}

const toneOf = (value: number): "positive" | "negative" => (value >= 0 ? "positive" : "negative");

/**
 * Which figure leads the summary (decided once, in one place):
 *  - "todo": the accumulated surplus, no consumption bar;
 *  - a month WITH income (logged, or the base income in "Este mes"): the final cash,
 *    with how much of the income was consumed (goal savings included);
 *  - a month WITHOUT income: the spending, asking for the income.
 * Pure: every number comes from `figures`; nothing is recalculated here.
 */
export function heroFigure(figures: SummaryFigures, ctx: HeroContext): HeroFigureData {
  const { period, accumulatedSurplus, money, now } = ctx;
  const { income, totalSpent, spentOnGoals, usesBaseFallback, referenceIncome } = figures;

  if (period === "todo") {
    return {
      kind: "excedente",
      label: "De toda tu historia",
      value: accumulatedSurplus,
      tone: toneOf(accumulatedSurplus),
      subtitle: "Excedente acumulado: tu plata libre, mes a mes.",
      bar: null,
      notes: [],
    };
  }

  const label = `Tu mes · ${monthName(figures.viewedMonth, now)}`;

  if (income <= 0) {
    return {
      kind: "gastos",
      label,
      value: totalSpent,
      tone: totalSpent > 0 ? "negative" : "positive",
      subtitle: "Gastos del mes. Registra tus ingresos para ver tu caja.",
      bar: null,
      notes: spentOnGoals > 0 ? [`Incluye ${money(spentOnGoals)} apartados a metas.`] : [],
    };
  }

  const pct = Math.round((totalSpent / income) * 1000) / 10;
  // Decided on the exact figures: 100,04% rounds to 100 but is still over the income.
  const over = totalSpent > income;
  const text = over ? "Gastaste más que tu ingreso" : `Consumido ${formatPercent(pct)} de tu ingreso`;
  const notes = [
    ...(spentOnGoals > 0 ? [`Incluye ${money(spentOnGoals)} apartados a metas.`] : []),
    ...(usesBaseFallback
      ? [
          `Usando tu ingreso base ${money(referenceIncome)}. Registra o actualiza el de este mes para ajustarlo.`,
        ]
      : []),
  ];

  return {
    kind: "caja",
    label,
    value: figures.cashAvailable,
    tone: toneOf(figures.cashAvailable),
    subtitle: figures.hasGoalFlow
      ? "Caja final: lo que te queda después de lo que pagaste y de lo que apartaste a metas."
      : "Caja final: lo que te queda después de lo que pagaste este mes.",
    bar: {
      pct,
      fill: Math.min(100, Math.max(0, pct)),
      over,
      text,
      valueText: `${text}${spentOnGoals > 0 ? ", incluye lo apartado a metas" : ""}`,
      spent: totalSpent,
      income,
    },
    notes,
  };
}
