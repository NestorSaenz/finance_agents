import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/ui/Logo";

export const metadata: Metadata = {
  title: "Guía · Safi",
  description:
    "Descubre todo lo que puedes hacer con Safi: registra gastos e ingresos hablando, controla tarjetas y presupuestos, ahorra para tus metas y consulta tus finanzas en lenguaje natural.",
};

/** Amount in tabular figures. Tone carries meaning via sign + color (never color alone). */
function Amt({
  tone = "plain",
  children,
}: {
  tone?: "in" | "out" | "plain";
  children: ReactNode;
}) {
  const sign = tone === "in" ? "+" : tone === "out" ? "−" : "";
  const color =
    tone === "in" ? "text-positive" : tone === "out" ? "text-negative" : "text-ink";
  return (
    <span className={`font-medium tabular-nums ${color}`}>
      {sign}
      {children}
    </span>
  );
}

/** Round gradient "S" avatar for Safi replies (mirrors the Logo mark's gradient). */
function SafiAvatar() {
  return (
    <span
      className="flex h-7 w-7 shrink-0 items-center justify-center self-end rounded-full bg-gradient-to-br from-brand-500 to-positive text-xs font-bold text-white shadow-sm"
      aria-hidden
    >
      S
    </span>
  );
}

function UserMsg({ children }: { children: ReactNode }) {
  return (
    <div className="flex justify-end" role="listitem">
      <span className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-br from-brand-500 to-positive px-3.5 py-2 text-sm text-white shadow-sm">
        {children}
      </span>
    </div>
  );
}

function SafiMsg({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-end justify-start gap-2" role="listitem">
      <SafiAvatar />
      <span className="max-w-[85%] rounded-2xl rounded-bl-md border border-line bg-surface px-3.5 py-2 text-sm text-ink shadow-card">
        {children}
      </span>
    </div>
  );
}

function Thread({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5" role="list" aria-label={label}>
      {children}
    </div>
  );
}

/** "Por debajo": a subtle left-bordered note revealing what Safi does under the hood. */
function Under({ children }: { children: ReactNode }) {
  return (
    <div className="mt-4 rounded-r-lg border-l-2 border-brand-500 bg-surface px-4 py-3 text-sm text-muted shadow-card">
      <span className="mb-1 block font-mono text-[0.65rem] font-semibold uppercase tracking-widest text-brand-700">
        Por debajo
      </span>
      {children}
    </div>
  );
}

/** Inline emphasis inside an Under note: neutral but weighted. */
function Em({ children }: { children: ReactNode }) {
  return <span className="font-medium text-ink">{children}</span>;
}

function Chapter({
  kicker,
  title,
  say,
  children,
}: {
  kicker: string;
  title: string;
  say?: string;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-line py-12 first:border-t-0 sm:py-14">
      <p className="font-mono text-xs uppercase tracking-wider text-brand-700">{kicker}</p>
      <h2 className="mt-1.5 text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h2>
      {say && <p className="mt-2 max-w-xl text-muted">{say}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

const CAPABILITIES = [
  "Gastos e ingresos",
  "Categorías automáticas y propias",
  "Efectivo o crédito",
  "Tarjetas con corte y pago",
  "Compras a cuotas",
  "Pagos y abonos a tarjeta",
  "Presupuestos con alertas",
  "Metas: aportar, retirar, ajustar",
  "Movimientos fijos (recurrentes)",
  "Extractos por foto o PDF",
  "Consultas por mes, tarjeta o categoría",
  "Análisis y consejos con tus datos",
  "Editar y borrar hablando",
  "Memoria de lo tuyo",
  "Panel: resumen y movimientos",
  "Excedente acumulado",
  "Disponible real (flujo de caja)",
];

export default function GuiaPage() {
  return (
    <div className="min-h-dvh bg-canvas text-ink">
      {/* Nav — mirrors the landing header */}
      <header className="sticky top-0 z-20 border-b border-line bg-surface/80 backdrop-blur">
        <nav className="mx-auto flex h-16 w-full max-w-3xl items-center justify-between px-4 sm:px-6">
          <Link href="/" aria-label="Ir al inicio de Safi">
            <Logo />
          </Link>
          <div className="flex items-center gap-2 sm:gap-3">
            <Link
              href="/login"
              className="inline-flex min-h-10 items-center rounded-xl px-3 text-sm font-medium text-muted transition-colors hover:bg-slate-100 hover:text-ink"
            >
              Iniciar sesión
            </Link>
            <Link
              href="/signup"
              className="inline-flex min-h-10 items-center rounded-xl bg-brand-600 px-4 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700"
            >
              Crear cuenta
            </Link>
          </div>
        </nav>
      </header>

      <main className="mx-auto w-full max-w-3xl px-4 sm:px-6">
        {/* Hero */}
        <section className="py-14 sm:py-20">
          <p className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">
            Asistente de finanzas conversacional
          </p>
          <h1 className="mt-4 text-4xl font-bold leading-[1.05] tracking-tight sm:text-6xl">
            Tu dinero,
            <br />
            <span className="bg-gradient-to-br from-brand-500 to-positive bg-clip-text text-transparent">
              hablando.
            </span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
            Le escribes a Safi como a un amigo. Él anota, categoriza, te avisa y te aconseja — sin
            formularios, sin hojas de cálculo, sin fricción.
          </p>

          <div className="mt-8">
            <Thread label="Ejemplo de conversación">
              <UserMsg>Gasté 45.000 en almuerzo</UserMsg>
              <SafiMsg>
                Listo ✅ <Amt tone="out">$45.000</Amt> en <strong>Restaurantes</strong>, hoy.
              </SafiMsg>
              <div className="flex items-end justify-start gap-2" role="listitem">
                <SafiAvatar />
                <span
                  className="inline-flex items-center gap-1 rounded-2xl rounded-bl-md border border-line bg-surface px-3.5 py-3 shadow-card"
                  aria-label="Safi está escribiendo"
                >
                  <span className="h-1.5 w-1.5 animate-blink rounded-full bg-muted" />
                  <span className="h-1.5 w-1.5 animate-blink rounded-full bg-muted [animation-delay:0.2s]" />
                  <span className="h-1.5 w-1.5 animate-blink rounded-full bg-muted [animation-delay:0.4s]" />
                </span>
              </div>
            </Thread>
          </div>

          <p className="mt-8 font-mono text-xs tracking-wide text-muted">
            baja y mira todo lo que le puedes decir{" "}
            <span aria-hidden className="text-brand-700">
              ↓
            </span>
          </p>
        </section>

        <Chapter
            kicker="01 · Ingresos y gastos"
            title="Anota hablando, en dos segundos"
            say="Gastos e ingresos, en lenguaje normal. Safi le pone categoría solo."
          >
            <Thread label="Registrar ingresos y gastos">
              <UserMsg>me pagaron 2.500.000 de sueldo</UserMsg>
              <SafiMsg>
                Anotado ✅ <Amt tone="in">$2.500.000</Amt> de ingreso.
              </SafiMsg>
              <UserMsg>40 lucas en gasolina</UserMsg>
              <SafiMsg>
                Hecho <Amt tone="out">$40.000</Amt> en <strong>Combustible</strong>.
              </SafiMsg>
            </Thread>
            <Under>
              Si no encaja en ninguna categoría conocida, Safi <Em>inventa una propia</Em> con
              sentido (“envíos”, “diezmo”, “niñera”) en vez de forzarla.
            </Under>
          </Chapter>

          <Chapter
            kicker="02 · Tarjetas de crédito"
            title="Entiende tu ciclo de la tarjeta"
            say="Registras tus tarjetas con su día de corte y de pago. Safi hace el resto."
          >
            <Thread label="Compra con tarjeta de crédito">
              <UserMsg>pagué 320.000 en Falabella con la tarjeta</UserMsg>
              <SafiMsg>
                Registrado 💳 <Amt tone="out">$320.000</Amt> (crédito, <strong>Falabella</strong>).
                <br />
                <span className="text-xs text-muted">
                  Afecta tu presupuesto de <strong className="font-medium">septiembre</strong>.
                </span>
              </SafiMsg>
            </Thread>
            <Under>
              El cargo impacta el mes en que <Em>pagas la tarjeta</Em> —según tu corte y pago—, no el
              día de la compra. Tu presupuesto no miente.
            </Under>
          </Chapter>

          <Chapter kicker="03 · Compras a cuotas" title="Diferido, sin sacar cuentas">
            <Thread label="Compra a cuotas">
              <UserMsg>compré una nevera de 1.200.000 a 6 cuotas</UserMsg>
              <SafiMsg>
                Listo. La reparto en <strong>6 cuotas</strong> de <Amt tone="out">$200.000</Amt>, una
                cada mes — no tienes que anotarlas una por una.
              </SafiMsg>
            </Thread>
          </Chapter>

          <Chapter kicker="04 · Presupuestos" title="Topes que te avisan">
            <Thread label="Presupuesto por categoría">
              <UserMsg>ponme un tope de 500.000 en restaurantes</UserMsg>
              <SafiMsg>
                Listo 🎯 Tope de <Amt>$500.000</Amt> en Restaurantes.
              </SafiMsg>
              <UserMsg>cómo voy?</UserMsg>
              <SafiMsg>
                Vas en <Amt tone="out">$410.000</Amt> de <Amt>$500.000</Amt> — <strong>82%</strong>.
                Te aviso si te pasas.
              </SafiMsg>
            </Thread>
          </Chapter>

          <Chapter
            kicker="05 · Metas de ahorro"
            title="Aparta, retira, ajusta"
            say="Ahorra para algo y muévelo cuando lo necesites — sin perder el rastro."
          >
            <Thread label="Metas de ahorro">
              <UserMsg>aparta 200.000 para el viaje a Japón</UserMsg>
              <SafiMsg>
                🎯 <Amt tone="in">$200.000</Amt> a «Japón». Llevas <Amt>$1.200.000</Amt> de{" "}
                <Amt>$8.000.000</Amt>.
              </SafiMsg>
              <UserMsg>retira 100.000 del fondo de emergencias</UserMsg>
              <SafiMsg>
                Retiré <Amt tone="in">$100.000</Amt>. Ese dinero{" "}
                <strong>vuelve a tu disponible</strong>.
              </SafiMsg>
            </Thread>
            <Under>
              Un retiro <Em>no es un ingreso</Em>: es tu propia plata de vuelta. No infla tus
              ganancias del mes — solo deja de estar apartada.
            </Under>
          </Chapter>

          <Chapter
            kicker="06 · Movimientos fijos"
            title="Lo de todos los meses, en automático"
          >
            <Thread label="Movimientos recurrentes">
              <UserMsg>cada mes pago 45.000 de gimnasio el día 1</UserMsg>
              <SafiMsg>
                Anotado 🔁 Cada día <strong>1</strong> registro <Amt tone="out">$45.000</Amt> de
                gimnasio. Tú no haces nada.
              </SafiMsg>
            </Thread>
            <Under>
              El sueldo, el arriendo, Netflix… los dices <Em>una sola vez</Em> y aparecen solos cada
              mes. Se acabó el registrarlos a mano.
            </Under>
          </Chapter>

          <Chapter kicker="07 · Extractos por foto" title="Mándale una captura del banco">
            <Thread label="Extracto por foto">
              <UserMsg>📷 extracto_agosto.jpg</UserMsg>
              <SafiMsg>
                Leí <strong>7 movimientos</strong> por <Amt>$1.480.000</Amt>. Te los propongo… ¿los
                registro?
              </SafiMsg>
              <UserMsg>sí, todos</UserMsg>
              <SafiMsg>Listos ✅ 7 movimientos guardados.</SafiMsg>
            </Thread>
            <Under>
              Foto, captura del Excel o PDF: Safi <Em>lee, entiende y propone</Em> antes de guardar
              nada. Tú solo confirmas.
            </Under>
          </Chapter>

          <Chapter
            kicker="08 · Pregúntale lo que sea (de tu plata)"
            title="Consultas y consejos con tus datos reales"
          >
            <Thread label="Consultas sobre tus finanzas">
              <UserMsg>en qué gasto más?</UserMsg>
              <SafiMsg>
                Este mes: <strong>Restaurantes</strong> <Amt>$410k</Amt> (32%),{" "}
                <strong>Transporte</strong> <Amt>$180k</Amt>, <strong>Mercado</strong>{" "}
                <Amt>$150k</Amt>…
              </SafiMsg>
              <UserMsg>cuánto llevo en la Nu este mes?</UserMsg>
              <SafiMsg>
                En tu <strong>Nu</strong>: <Amt tone="out">$643.000</Amt> en 9 movimientos.
              </SafiMsg>
              <UserMsg>dame consejos para ahorrar</UserMsg>
              <SafiMsg>
                El 32% se te va en restaurantes. Si cocinas 2 días más a la semana liberas ~
                <Amt tone="in">$160.000</Amt>/mes para tu meta de Japón 🇯🇵
              </SafiMsg>
            </Thread>
          </Chapter>

          <Chapter kicker="09 · Corrige hablando" title="Editar y borrar, sin menús ni IDs">
            <Thread label="Corregir y borrar movimientos">
              <UserMsg>ese último fue en efectivo, no con tarjeta</UserMsg>
              <SafiMsg>Corregido ✏️ ahora en efectivo.</SafiMsg>
              <UserMsg>borra el gasto de Netflix</UserMsg>
              <SafiMsg>
                🗑️ Borré <strong>Netflix</strong> <Amt tone="out">$16.900</Amt>.
              </SafiMsg>
            </Thread>
            <Under>
              Lo encuentra por <Em>lo que le digas</Em> —descripción, monto, fecha— y confirma antes
              de borrar. Nada de códigos.
            </Under>
          </Chapter>

          <Chapter
            kicker="10 · Dos detalles que enamoran"
            title="Te recuerda quién eres. Y no se distrae."
          >
            <Thread label="Memoria y enfoque">
              <UserMsg>soy freelance y cobro en dólares</UserMsg>
              <SafiMsg>
                Anotado 🧠 lo tendré en cuenta cuando hablemos de tus ingresos.
              </SafiMsg>
              <UserMsg>escríbeme un poema sobre el mar</UserMsg>
              <SafiMsg>Jeje, de eso no soy — pero de tu plata, lo que quieras 🙂</SafiMsg>
            </Thread>
          </Chapter>

          {/* Dashboard peek — reuses the SummaryContent "Flujo de caja" styling */}
          <Chapter
            kicker="Y cuando prefieras verlo"
            title="Un panel que dice la verdad"
            say="Todo lo que hablas se ve, ordenado. Con tu disponible real y tu excedente que se acumula mes a mes."
          >
            <div
              className="rounded-xl border border-line bg-surface p-4 shadow-card"
              role="img"
              aria-label="Vista del panel de resumen de Safi: flujo de caja del mes con un disponible real de $6.470.466"
            >
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                Flujo de caja · este mes
              </p>
              <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-positive">
                $6.470.466
              </p>
              <dl className="mt-3 flex flex-col gap-1 text-sm">
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Ingresos</dt>
                  <dd className="tabular-nums text-positive">+$15.454.900</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Efectivo</dt>
                  <dd className="tabular-nums text-negative">−$5.273.858</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Pagos a tarjetas</dt>
                  <dd className="tabular-nums text-negative">−$2.610.576</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Aportes a metas</dt>
                  <dd className="tabular-nums text-negative">−$1.100.000</dd>
                </div>
                <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5">
                  <dt className="font-medium text-ink">Disponible real</dt>
                  <dd className="font-semibold tabular-nums text-positive">$6.470.466</dd>
                </div>
              </dl>
              <div className="mt-4 flex flex-col gap-3">
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-sm">
                    <span className="text-ink">Restaurantes</span>
                    <span className="tabular-nums text-muted">$643k / $700k</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-amber-500" style={{ width: "92%" }} />
                  </div>
                </div>
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-sm">
                    <span className="text-ink">🎯 Viaje a Japón</span>
                    <span className="tabular-nums text-muted">$1.20M / $8.00M</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-brand-500 to-positive"
                      style={{ width: "15%" }}
                    />
                  </div>
                </div>
              </div>
            </div>
            <Under>
              La pestaña <Em>Movimientos</Em> junta todo: efectivo, tarjetas, aportes y retiros de
              metas — con filtros por fuente. Nada se pierde.
            </Under>
          </Chapter>

          {/* Capabilities pill cloud */}
          <Chapter kicker="De un vistazo" title="Todo lo que puedes hacer">
            <ul className="flex flex-wrap gap-2">
              {CAPABILITIES.map((cap) => (
                <li
                  key={cap}
                  className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-ink"
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden />
                  {cap}
                </li>
              ))}
            </ul>
          </Chapter>

          {/* Closing CTA */}
          <section className="border-t border-line py-16 text-center">
            <p className="font-mono text-xs uppercase tracking-wider text-brand-700">Empieza ahora</p>
            <h2 className="mt-1.5 text-2xl font-bold tracking-tight text-ink sm:text-3xl">
              Solo escríbele.
            </h2>
            <div
              className="mx-auto mt-6 flex max-w-md items-center gap-2 rounded-full border border-line bg-surface py-2 pl-4 pr-2 text-left shadow-card"
              aria-hidden
            >
              <span className="flex-1 truncate text-sm text-muted">
                Gasté 30.000 en un café con…
              </span>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-positive text-white">
                ↑
              </span>
            </div>
            <Link
              href="/signup"
              className="mt-7 inline-flex min-h-12 items-center justify-center rounded-xl bg-brand-600 px-7 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700"
            >
              Crear cuenta gratis
            </Link>
          </section>
      </main>

      {/* Footer — mirrors the landing footer */}
      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-3xl flex-col items-center justify-between gap-3 px-4 py-8 text-sm text-muted sm:flex-row sm:px-6">
          <Link href="/" aria-label="Ir al inicio de Safi">
            <Logo />
          </Link>
          <p>© 2026 Safi · Tu dinero, hablando.</p>
        </div>
      </footer>
    </div>
  );
}
