import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/ui/Logo";

export const metadata: Metadata = {
  title: "Guía · Safi",
  description:
    "Descubre todo lo que puedes hacer con Safi: registra gastos e ingresos hablando, controla tarjetas y presupuestos, ahorra para tus metas (con plan mensual), valida tus extractos contra lo que ya registraste y consulta tus finanzas en lenguaje natural.",
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
    tone === "in" ? "text-emerald-700" : tone === "out" ? "text-negative" : "text-ink";
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
  "Cambio de corte con confirmación",
  "Compras a cuotas",
  "Pagos y abonos a tarjeta",
  "Presupuestos con alertas",
  "Tus topes como % de tu ingreso",
  "Metas: aportar, retirar, ajustar",
  "Plan mensual de metas",
  "Movimientos fijos (recurrentes)",
  "Extractos por foto o PDF",
  "Validar extractos contra lo registrado",
  "Consultas por mes, tarjeta o categoría",
  "Análisis y consejos con tus datos",
  "Editar y borrar hablando",
  "Memoria de lo tuyo",
  "Panel: resumen y movimientos",
  "Excedente acumulado",
  "Tu caja real del mes (flujo de caja)",
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
            <div className="mt-6">
              <Thread label="Cambiar el corte de una tarjeta">
                <UserMsg>cambia el corte de Rappi al 20</UserMsg>
                <SafiMsg>
                  Rappi: corte <strong>15 → 20</strong>, el día de pago sigue el 5. ¿Lo cambio?
                </SafiMsg>
                <UserMsg>sí</UserMsg>
                <SafiMsg>
                  ✏️ Actualicé tu tarjeta Rappi: corte: día 15 → 20. Recalculé{" "}
                  <strong>4 cargos</strong> pendientes con las nuevas fechas.
                </SafiMsg>
              </Thread>
            </div>
            <Under>
              Cambiar el día de <Em>corte o de pago</Em> siempre pasa por una confirmación: Safi te
              propone el cambio y solo lo aplica cuando le dices que sí. Al confirmar,{" "}
              <Em>recalcula en qué mes cae cada cargo pendiente</Em>; los estados ya vencidos
              conservan su mes. El nombre y el cupo sí cambian al instante.
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
            <Under>
              La barra <Em>incluye tus gastos fijos</Em> (arriendo, colegio, suscripciones). La
              alerta te avisa cuando tus gastos <Em>variables</Em> se acercan al tope o cuando ya
              te pasaste — no cada mes solo porque llegó una cuenta fija. Si tus gastos fijos ya
              ocupan casi todo el tope, el aviso llega cuando te pasas.
            </Under>
            <Under>
              En el panel, arriba de tus topes ves <Em>“Tus topes suman $X · % de tu ingreso”</Em>
              (sobre tu ingreso base) y cada tope con su propio % del ingreso. Si tienes un tope
              general, aparece aparte para no sumarlo dos veces. Cuando preguntas “¿cómo voy?”, el
              chat te da los totales ya calculados. Los planes de tus metas se muestran{" "}
              <Em>aparte</Em> (“Ahorro planificado del mes” y “Topes + metas”): no se suman al total
              de tus topes ni a tus gastos.
            </Under>
          </Chapter>

          <Chapter
            kicker="05 · Metas de ahorro"
            title="Aparta, retira, ajusta"
            say="Ahorra para algo y muévelo cuando lo necesites — sin perder el rastro."
          >
            <Thread label="Metas de ahorro">
              <UserMsg>abona 200.000 al viaje a Japón</UserMsg>
              <SafiMsg>
                ✅ Aboné <Amt>$200.000</Amt> a «Viaje a Japón» (cuenta en tus gastos del mes como
                ahorro). Llevas <Amt>$1.200.000</Amt> de <Amt>$8.000.000</Amt>.
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

            <div className="mt-8">
              <p className="mb-3 text-sm font-medium text-ink">
                Y puedes planear cuánto aportar cada mes
              </p>
              <Thread label="Plan mensual de una meta">
                <UserMsg>para noviembre aparta 500.000 a la meta de vacaciones</UserMsg>
                <SafiMsg>
                  ✅ Plan de <strong>Vacaciones</strong>: <Amt>$500.000</Amt> (solo noviembre 2026).
                  Quedó como <strong>plan</strong>: no es un tope ni un gasto, y aún no has aportado.
                  Cuando muevas la plata, dime «aporté X a Vacaciones» y lo registro; ahí sí contará
                  en tus gastos del mes.
                </SafiMsg>
                <UserMsg>de ahora en adelante abona 300.000 al mes al fondo de emergencias</UserMsg>
                <SafiMsg>
                  ✅ Plan de <strong>Fondo de emergencias</strong>: <Amt>$300.000</Amt> (desde
                  noviembre 2026 en adelante). Quedó como plan (no es un tope ni un gasto, y aún no has
                  aportado).
                </SafiMsg>
                <UserMsg>quita el plan de diciembre del fondo de emergencias</UserMsg>
                <SafiMsg>
                  ✅ Quité el plan de Fondo de emergencias para diciembre 2026: ese mes no planeas
                  abonar.
                </SafiMsg>
                <UserMsg>abona 200.000 a vacaciones</UserMsg>
                <SafiMsg>
                  ✅ Aboné <Amt>$200.000</Amt> a «Vacaciones» (cuenta en tus gastos del mes como
                  ahorro). Llevas <Amt>$200.000</Amt> de <Amt>$3.000.000</Amt>.
                </SafiMsg>
                <UserMsg>¿cómo voy con mis metas este mes?</UserMsg>
                <SafiMsg>
                  Vacaciones: plan <Amt>$500.000</Amt> · aportado <Amt>$200.000</Amt> (40%) · faltan{" "}
                  <Amt>$300.000</Amt>
                  <br />
                  Fondo de emergencias: plan <Amt>$300.000</Amt> · aportado <Amt>$0</Amt> (0%) · faltan{" "}
                  <Amt>$300.000</Amt>
                  <br />
                  TOTAL PLAN METAS (el plan no es gasto; lo aportado sí cuenta en tus gastos del
                  mes): planificado <Amt>$800.000</Amt> · aportado <Amt>$200.000</Amt>
                </SafiMsg>
              </Thread>
              <Under>
                Para <Em>quitar o cambiar</Em> un plan: “quita el plan de diciembre” deja ese mes sin
                plan, “en diciembre vuelve al plan normal” lo regresa al general y “ya no quiero
                planear más para Vacaciones” deja de planear desde ese mes en adelante. Si el mes ya
                pasó, Safi <Em>te pide confirmación antes de escribir</Em> y no cambia nada hasta que
                le dices que sí.
              </Under>
              <Under>
                <Em>Plan, aporte, gasto y tope no son lo mismo.</Em> Un plan es una intención: no
                mueve plata. Un aporte es plata que realmente apartaste, y{" "}
                <Em>cuenta en tus gastos del mes</Em> (desde noviembre de 2026; antes de esa fecha
                queda registrado pero no cuenta). Un retiro no es ingreso. Y un tope es el límite de
                una categoría de gasto: si le dices “tope mensual” a una meta, Safi lo toma como plan
                y te aclara que quedó como plan, no como tope.
              </Under>
            </div>
          </Chapter>

          <Chapter
            kicker="06 · Movimientos fijos"
            title="Lo de todos los meses, en automático"
          >
            <Thread label="Movimientos recurrentes">
              <UserMsg>cada mes pago 45.000 de gimnasio el día 1, en efectivo</UserMsg>
              <SafiMsg>
                Anotado 🔁 Cada día <strong>1</strong> registro <Amt tone="out">$45.000</Amt> de
                gimnasio. Tú no haces nada.
              </SafiMsg>
            </Thread>
            <Under>
              El sueldo, el arriendo, Netflix… los dices <Em>una sola vez</Em> y aparecen solos cada
              mes. Se acabó el registrarlos a mano. Si tienes tarjetas y no dices cómo se paga, Safi
              te pregunta si es en efectivo o con tarjeta de crédito antes de crearlo.
            </Under>
          </Chapter>

          <Chapter kicker="07 · Extractos por foto" title="Mándale una captura del banco">
            <Thread label="Extracto por foto">
              <UserMsg>📷 extracto_agosto.jpg</UserMsg>
              <SafiMsg>
                Leí <strong>7 movimientos</strong> y ninguno estaba registrado.
                <br />
                <br />
                Faltan por registrar: …
                <br />
                <br />
                Los categorizo yo y te muestro cómo quedaron. ¿Los registro tal cual? Dime{" "}
                <em>sí</em> para guardarlos, o indícame qué corregir.
              </SafiMsg>
              <UserMsg>sí, todos</UserMsg>
              <SafiMsg>Listos ✅ 7 movimientos guardados.</SafiMsg>
            </Thread>
            <Under>
              Foto, captura del Excel o PDF: Safi <Em>lee, entiende y propone</Em> antes de guardar
              nada. Tú solo confirmas.
            </Under>
            <div className="mt-6">
              <Thread label="Validar un extracto contra lo registrado">
                <UserMsg>📷 extracto_nu.jpg — valida que todos estos movimientos de Nu estén registrados</UserMsg>
                <SafiMsg>
                  Revisé <strong>7 movimientos</strong> contra tus registros: 5 ya están registrados.
                  <br />✅ Farmacia: <Amt>$32.000</Amt> (2026-10-08)
                  <br />💳 pago a tu Nu del 12-oct ya registrado
                  <br />…
                  <br />
                  <br />
                  Faltan por registrar: Café <Amt tone="out">$9.500</Amt> y Taxi{" "}
                  <Amt tone="out">$18.000</Amt>. ¿Los registro tal cual?
                </SafiMsg>
              </Thread>
            </div>
            <Under>
              También sirve preguntar “¿falta alguno por registrar?”. Safi compara cada línea con lo
              que ya tienes, marca con ✅ lo que está y propone registrar <Em>solo lo que falta</Em>:
              no te pregunta categoría por línea (las pone él) y, como mucho, una sola pregunta sobre
              cómo pagaste si no se ve en el extracto. Un “Gracias por tu pago” del banco lo reconoce
              como <Em>pago a la tarjeta</Em>, no como ingreso.
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
                ¿Elimino tu gasto de <Amt tone="out">$16.900</Amt> en Suscripciones del 3 de octubre?
              </SafiMsg>
              <UserMsg>sí</UserMsg>
              <SafiMsg>
                🗑️ Eliminé: <strong>Netflix</strong> — <Amt tone="out">$16.900</Amt> (2026-10-03).
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
            say="Todo lo que hablas se ve, ordenado. Con tu caja real del mes (lo que apartas a metas cuenta en tus gastos del mes, pero sigue siendo tuyo), el plan de tus metas y tu excedente que se acumula."
          >
            <div
              className="rounded-xl border border-line bg-surface p-4 shadow-card"
              role="img"
              aria-label="Vista del panel de resumen de Safi: flujo de caja del mes con una caja final de $6.470.466 y un plan de metas por aportar de $600.000"
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
                <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5">
                  <dt className="font-medium text-ink">Te sobró</dt>
                  <dd className="font-semibold tabular-nums text-positive">$7.570.466</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted">Apartado para metas</dt>
                  <dd className="tabular-nums text-brand-600">−$1.100.000</dd>
                </div>
                <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5">
                  <dt className="font-medium text-ink">Caja final del mes</dt>
                  <dd className="font-semibold tabular-nums text-positive">$6.470.466</dd>
                </div>
              </dl>
              <p className="mt-3 text-xs text-muted">
                Por aportar a tus metas este mes (plan):{" "}
                <span className="font-semibold tabular-nums text-ink">$600.000</span>. Es un plan: no
                cuenta como gasto hasta que registres el aporte.
              </p>
              <div className="mt-4 flex flex-col gap-3">
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-sm">
                    <span className="text-ink">Restaurantes</span>
                    <span className="tabular-nums text-muted">$410k / $500k</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-brand-600" style={{ width: "82%" }} />
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
              metas — con filtros por fuente. Nada se pierde. En <Em>“Todas”</Em> el “gastado” es el
              mismo número que <Em>Gastos</Em> en el Resumen.
            </Under>
            <Under>
              <Em>Gastos</Em> incluye lo que ya apartaste a tus metas, con el desglose “consumo +
              apartado a metas”; el <Em>Balance</Em> y <Em>Gastos vs ingresos</Em> también lo
              incluyen (para aportes desde noviembre de 2026). Tu <Em>caja final no cambia</Em>: ya
              descontaba lo apartado. La línea “Por aportar a tus metas este mes (plan)” solo
              aparece en el mes actual y es informativa: el plan no cuenta como gasto hasta que
              aportes.
            </Under>
            <Under>
              Con el selector de mes ves cualquier mes. El bloque <Em>“Ahorro planificado del mes”</Em>{" "}
              sigue al mes que elijas y el <Em>“Historial de planes (últimos 5 meses)”</Em> te deja
              tocar un mes para verlo. Los topes, en cambio, solo se muestran para el mes en curso.
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
