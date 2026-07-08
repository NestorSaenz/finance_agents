"use client";

import { BarChart3, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

import { Logo } from "@/components/ui/Logo";
import { useAuth } from "@/context/AuthContext";

interface HeaderProps {
  onNewChat: () => void;
  onOpenDashboard: () => void;
}

export function Header({ onNewChat, onOpenDashboard }: HeaderProps) {
  const router = useRouter();
  const { user, logout } = useAuth();

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-3xl items-center justify-between px-4">
        <button
          onClick={onNewChat}
          className="rounded-lg transition-opacity hover:opacity-80"
          aria-label="Nueva conversación"
        >
          <Logo />
        </button>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            onClick={onOpenDashboard}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-muted transition-colors hover:bg-slate-100 hover:text-ink"
          >
            <BarChart3 className="h-4 w-4" aria-hidden />
            <span className="hidden sm:inline">Resumen</span>
          </button>
          {user?.email && (
            <span className="hidden max-w-[12rem] truncate text-sm text-muted md:inline">
              {user.email}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-muted transition-colors hover:bg-slate-100 hover:text-ink"
          >
            <LogOut className="h-4 w-4" aria-hidden />
            <span className="hidden sm:inline">Salir</span>
          </button>
        </div>
      </div>
    </header>
  );
}
