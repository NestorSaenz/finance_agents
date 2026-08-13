"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ChatView, type ChatViewHandle } from "@/components/chat/ChatView";
import { DashboardPanel } from "@/components/dashboard/DashboardPanel";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { Header } from "@/components/layout/Header";
import { Spinner } from "@/components/ui/Spinner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function ChatPage() {
  const router = useRouter();
  const { token, loading } = useAuth();
  const chatRef = useRef<ChatViewHandle>(null);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [dashboardRefreshKey, setDashboardRefreshKey] = useState(0);
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Redirect unauthenticated users once hydration has settled.
  useEffect(() => {
    if (!loading && !token) router.replace("/login");
  }, [loading, token, router]);

  // Show the onboarding wizard once, when the profile isn't yet onboarded.
  useEffect(() => {
    if (loading || !token) return;
    let active = true;
    api
      .profile(token)
      .then((profile) => {
        if (active && !profile.onboarding_completed) setShowOnboarding(true);
      })
      .catch(() => {
        /* non-blocking: if the profile can't load, skip the wizard */
      });
    return () => {
      active = false;
    };
  }, [loading, token]);

  if (loading || !token) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-canvas text-muted">
        <Spinner className="h-6 w-6" />
      </main>
    );
  }

  return (
    <div className="flex h-dvh flex-col bg-canvas">
      <Header
        onNewChat={() => chatRef.current?.reset()}
        onOpenDashboard={() => setDashboardOpen(true)}
      />
      {/* Chat + panel share the row: on lg+ the open panel is a real column that
          shrinks the chat (no overlap); below lg it's a drawer over the chat. */}
      <div className="flex min-h-0 flex-1">
        <ChatView
          ref={chatRef}
          onDataChanged={() => setDashboardRefreshKey((k) => k + 1)}
        />
        <DashboardPanel
          open={dashboardOpen}
          onClose={() => setDashboardOpen(false)}
          refreshKey={dashboardRefreshKey}
        />
      </div>
      {showOnboarding && (
        <OnboardingWizard onDone={() => setShowOnboarding(false)} />
      )}
    </div>
  );
}
