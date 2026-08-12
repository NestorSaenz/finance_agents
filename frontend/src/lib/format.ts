// Presentation helpers shared across the UI (money, category labels).

/** Human-readable Spanish labels for backend category slugs. */
const CATEGORY_LABELS: Record<string, string> = {
  alimentacion: "Alimentación",
  transporte: "Transporte",
  vivienda: "Vivienda",
  servicios: "Servicios",
  salud: "Salud",
  entretenimiento: "Entretenimiento",
  educacion: "Educación",
  ropa: "Ropa",
  tecnologia: "Tecnología",
  viajes: "Viajes",
  restaurantes: "Restaurantes",
  combustible: "Combustible",
  estacionamiento: "Estacionamiento",
  suscripciones: "Suscripciones",
  gimnasio: "Gimnasio",
  mascotas: "Mascotas",
  regalos: "Regalos",
  imprevistos: "Imprevistos",
  otros: "Otros",
};

export function categoryLabel(slug: string): string {
  return CATEGORY_LABELS[slug] ?? slug.charAt(0).toUpperCase() + slug.slice(1);
}

// Currencies with no minor unit in everyday use: amounts are shown as whole
// numbers (e.g. COP $1000, not $1000,00). Everything else keeps Intl's
// per-currency default (USD/MXN/EUR/PEN → 2 decimals).
const ZERO_DECIMAL_CURRENCIES = new Set([
  "COP",
  "CLP",
  "PYG",
  "JPY",
  "KRW",
  "VND",
  "ISK",
  "HUF",
  "XAF",
  "XOF",
]);

// One Intl.NumberFormat per currency, built lazily and reused (formatters are
// relatively expensive to construct, and formatMoney runs on every row).
const formatterCache = new Map<string, Intl.NumberFormat>();

function formatterFor(currency: string): Intl.NumberFormat {
  let formatter = formatterCache.get(currency);
  if (!formatter) {
    formatter = new Intl.NumberFormat("es", {
      style: "currency",
      currency,
      // Each user has a single currency, so the narrow symbol reads cleanly as
      // "$" instead of "MX$"/"COP".
      currencyDisplay: "narrowSymbol",
      ...(ZERO_DECIMAL_CURRENCIES.has(currency)
        ? { maximumFractionDigits: 0 }
        : {}),
    });
    formatterCache.set(currency, formatter);
  }
  return formatter;
}

/**
 * Format a decimal string (from the API) as currency in the user's currency.
 * Defaults to COP so existing call sites keep working until a currency is
 * threaded in. Zero-decimal currencies (COP, CLP, JPY, …) drop the cents;
 * others keep Intl's default minor units.
 */
export function formatMoney(
  value: string | number,
  currency: string = "COP",
): string {
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) return "—";
  return formatterFor(currency).format(amount);
}

/** Format an ISO date (YYYY-MM-DD) as a short "3 jul" label. */
export function formatDayMonth(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("es-ES", { day: "numeric", month: "short" });
}
