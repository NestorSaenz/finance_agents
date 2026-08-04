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

const currencyFormatter = new Intl.NumberFormat("es-MX", {
  style: "currency",
  currency: "MXN",
  maximumFractionDigits: 0,
});

/** Format a decimal string (from the API) as MXN currency. */
export function formatMoney(value: string | number): string {
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) return "—";
  return currencyFormatter.format(amount);
}

/** Format an ISO date (YYYY-MM-DD) as a short "3 jul" label. */
export function formatDayMonth(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("es-ES", { day: "numeric", month: "short" });
}
