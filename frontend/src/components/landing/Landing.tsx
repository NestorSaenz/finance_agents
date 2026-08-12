import {
  ArrowRight,
  BarChart3,
  MessageSquare,
  PiggyBank,
  ShieldCheck,
  Target,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/ui/Logo";

const FEATURES = [
  {
    icon: MessageSquare,
    title: "Registra hablando",
    body: "“Gasté 200.000 en el súper” y listo. Safi lo categoriza y lo guarda por ti.",
  },
  {
    icon: BarChart3,
    title: "Entiende tus gastos",
    body: "Pregunta “¿en qué gasto más?” y recibe un análisis claro al instante.",
  },
  {
    icon: Wallet,
    title: "Presupuestos con alertas",
    body: "Fija topes por categoría y Safi te avisa antes de que te pases.",
  },
  {
    icon: Target,
    title: "Metas de ahorro",
    body: "Define objetivos, registra abonos y sigue tu progreso mes a mes.",
  },
];

const STEPS = [
  { n: "1", title: "Crea tu cuenta", body: "Gratis y en segundos, sin tarjetas ni configuraciones." },
  { n: "2", title: "Escríbele a Safi", body: "Cuéntale tus gastos e ingresos en lenguaje natural." },
  { n: "3", title: "Gana claridad", body: "Consulta, presupuesta y ahorra con respuestas al momento." },
];

export function Landing() {
  return (
    <div className="min-h-dvh bg-canvas text-ink">
      {/* Nav */}
      <header className="sticky top-0 z-20 border-b border-line bg-surface/80 backdrop-blur">
        <nav className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Logo />
          <div className="flex items-center gap-2 sm:gap-3">
            <Link
              href="/guia"
              className="hidden min-h-10 items-center rounded-xl px-3 text-sm font-medium text-muted transition-colors hover:bg-slate-100 hover:text-ink sm:inline-flex"
            >
              Guía
            </Link>
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

      {/* Hero */}
      <section className="mx-auto grid w-full max-w-6xl items-center gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-2 lg:gap-12">
        <div className="animate-fade-in-up">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
            Tus finanzas, bajo control
          </span>
          <h1 className="mt-4 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
            Controla tu dinero <span className="text-brand-600">conversando</span>.
          </h1>
          <p className="mt-4 max-w-md text-base leading-relaxed text-muted sm:text-lg">
            Registra gastos, vigila presupuestos y planifica tu ahorro escribiéndole a Safi como a
            un amigo. Sin hojas de cálculo ni formularios.
          </p>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <Link
              href="/signup"
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand-600 px-6 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700"
            >
              Crear cuenta gratis
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
            <Link
              href="/login"
              className="inline-flex min-h-12 items-center justify-center rounded-xl border border-line bg-surface px-6 text-sm font-semibold text-ink transition-colors hover:bg-slate-50"
            >
              Ya tengo cuenta
            </Link>
          </div>
          <Link
            href="/guia"
            className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-700 underline-offset-4 hover:underline"
          >
            Ver qué puedes hacer
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>

        {/* Chat preview mockup */}
        <div className="animate-fade-in-up rounded-2xl border border-line bg-surface p-4 shadow-pop sm:p-6">
          <div className="mb-4 flex items-center gap-2 border-b border-line pb-3">
            <Logo withWordmark={false} />
            <span className="text-sm font-semibold">Safi</span>
            <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-positive">
              <span className="h-2 w-2 rounded-full bg-positive" /> en línea
            </span>
          </div>
          <div className="flex flex-col gap-3 text-sm">
            <ChatBubble side="user">gasté 350.000 en el súper</ChatBubble>
            <ChatBubble side="bot">
              ✅ Registré <strong>$350.000</strong> en <strong>alimentación</strong> (hoy).
            </ChatBubble>
            <ChatBubble side="user">¿en qué gasto más este mes?</ChatBubble>
            <ChatBubble side="bot">
              Tu mayor gasto es <strong>Restaurantes</strong> (38%), seguido de{" "}
              <strong>Alimentación</strong> (26%). 💡 Reducir salidas te ahorraría ~$900.000/mes.
            </ChatBubble>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-line bg-surface">
        <div className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
          <div className="mx-auto max-w-xl text-center">
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              Todo tu dinero, en una conversación
            </h2>
            <p className="mt-3 text-muted">
              Safi entiende lenguaje natural y hace el trabajo pesado por ti.
            </p>
          </div>
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="rounded-2xl border border-line bg-canvas p-5 shadow-card">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <h3 className="mt-4 font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
        <h2 className="text-center text-2xl font-bold tracking-tight sm:text-3xl">
          Empezar toma un minuto
        </h2>
        <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-3">
          {STEPS.map(({ n, title, body }) => (
            <div key={n} className="text-center">
              <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-brand-600 text-sm font-bold text-white">
                {n}
              </span>
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA band */}
      <section className="border-t border-line bg-surface">
        <div className="mx-auto w-full max-w-3xl px-4 py-16 text-center sm:px-6">
          <PiggyBank className="mx-auto h-10 w-10 text-brand-600" aria-hidden />
          <h2 className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl">
            Toma el control de tus finanzas hoy
          </h2>
          <p className="mt-3 text-muted">Es gratis y solo toma un minuto empezar.</p>
          <Link
            href="/signup"
            className="mt-7 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand-600 px-7 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700"
          >
            Crear cuenta gratis
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-3 px-4 py-8 text-sm text-muted sm:flex-row sm:px-6">
          <Logo />
          <p>© {"2026"} Safi · Tu asistente de finanzas personales</p>
        </div>
      </footer>
    </div>
  );
}

function ChatBubble({ side, children }: { side: "user" | "bot"; children: React.ReactNode }) {
  const isUser = side === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <span
        className={`max-w-[80%] rounded-2xl px-3.5 py-2 ${
          isUser
            ? "rounded-br-md bg-brand-600 text-white"
            : "rounded-bl-md border border-line bg-canvas text-ink"
        }`}
      >
        {children}
      </span>
    </div>
  );
}
