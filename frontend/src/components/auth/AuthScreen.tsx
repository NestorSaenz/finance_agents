"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Logo } from "@/components/ui/Logo";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";

type Mode = "login" | "signup";

const COPY: Record<Mode, { title: string; cta: string; alt: string; altHref: string; altText: string }> = {
  login: {
    title: "Inicia sesión",
    cta: "Entrar",
    alt: "¿No tienes cuenta?",
    altHref: "/signup",
    altText: "Crea una",
  },
  signup: {
    title: "Crea tu cuenta",
    cta: "Registrarme",
    alt: "¿Ya tienes cuenta?",
    altHref: "/login",
    altText: "Inicia sesión",
  },
};

/** Map backend/API errors to friendly, actionable Spanish copy. */
function friendlyError(err: unknown, mode: Mode): string {
  if (!(err instanceof ApiError)) return "Ocurrió un error. Inténtalo de nuevo.";
  const raw = err.message.toLowerCase();
  if (mode === "signup" && raw.includes("already registered")) {
    return "Ese correo ya tiene una cuenta. Inicia sesión.";
  }
  if (err.status === 401 || raw.includes("invalid") || raw.includes("credentials")) {
    return "Correo o contraseña incorrectos.";
  }
  return err.message;
}

export function AuthScreen({ mode }: { mode: Mode }) {
  const router = useRouter();
  const { login, signup, token, loading: authLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const copy = COPY[mode];

  // Already authenticated -> go straight to the chat.
  useEffect(() => {
    if (!authLoading && token) router.replace("/chat");
  }, [authLoading, token, router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login({ email: email.trim(), password });
      } else {
        await signup({ email: email.trim(), password });
      }
      router.replace("/chat");
    } catch (err) {
      setError(friendlyError(err, mode));
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo />
          <p className="mt-3 text-sm text-muted">Tu asistente de finanzas personales</p>
        </div>

        <div className="rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-7">
          <h1 className="mb-5 text-xl font-semibold text-ink">{copy.title}</h1>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            <Input
              label="Correo"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="tucorreo@ejemplo.com"
            />
            <Input
              label="Contraseña"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Mínimo 8 caracteres"
            />

            {error && (
              <p
                role="alert"
                className="rounded-xl border border-negative/20 bg-red-50 px-3 py-2 text-sm text-negative"
              >
                {error}
              </p>
            )}

            <Button type="submit" loading={submitting} className="mt-1 w-full">
              {copy.cta}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-center text-sm text-muted">
          {copy.alt}{" "}
          <Link href={copy.altHref} className="font-medium text-brand-600 hover:text-brand-700">
            {copy.altText}
          </Link>
        </p>
      </div>
    </main>
  );
}
