"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Landing } from "@/components/landing/Landing";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/context/AuthContext";

export default function HomePage() {
  const router = useRouter();
  const { token, loading } = useAuth();

  // Send authenticated users straight to the app.
  useEffect(() => {
    if (!loading && token) router.replace("/chat");
  }, [loading, token, router]);

  if (loading || token) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-canvas text-muted">
        <Spinner className="h-6 w-6" />
      </main>
    );
  }

  return <Landing />;
}
