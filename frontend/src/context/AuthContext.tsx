"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { AuthUser, LoginPayload, SessionResponse, SignupPayload } from "@/lib/types";

const TOKEN_KEY = "fg_token";
const REFRESH_KEY = "fg_refresh";
const USER_KEY = "fg_user";

// Supabase access tokens last ~1h; refresh comfortably before that.
const REFRESH_INTERVAL_MS = 45 * 60 * 1000;

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  /** True until localStorage has been read on the client (avoids redirect flicker). */
  loading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  signup: (payload: SignupPayload) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Kept in a ref (not state) so the refresh timer always reads the latest token
  // without re-subscribing.
  const refreshTokenRef = useRef<string | null>(null);

  const persist = useCallback((session: SessionResponse) => {
    const nextUser: AuthUser = { userId: session.user_id, email: session.email };
    localStorage.setItem(TOKEN_KEY, session.access_token);
    localStorage.setItem(REFRESH_KEY, session.refresh_token);
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    refreshTokenRef.current = session.refresh_token;
    setToken(session.access_token);
    setUser(nextUser);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
    refreshTokenRef.current = null;
    setToken(null);
    setUser(null);
  }, []);

  // Hydrate from localStorage once on mount, then refresh the access token so a
  // session that sat idle past its expiry comes back alive (instead of erroring).
  useEffect(() => {
    let active = true;
    const storedToken = localStorage.getItem(TOKEN_KEY);
    const storedRefresh = localStorage.getItem(REFRESH_KEY);
    const storedUser = localStorage.getItem(USER_KEY);

    if (!storedToken || !storedRefresh || !storedUser) {
      setLoading(false);
      return;
    }

    try {
      setToken(storedToken);
      setUser(JSON.parse(storedUser) as AuthUser);
      refreshTokenRef.current = storedRefresh;
    } catch {
      logout();
      setLoading(false);
      return;
    }

    // Best-effort refresh; if the refresh token is also dead, log out cleanly.
    api
      .refresh(storedRefresh)
      .then((session) => {
        if (active) persist(session);
      })
      .catch(() => {
        if (active) logout();
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [persist, logout]);

  // Proactively refresh while logged in so the token never expires mid-use.
  useEffect(() => {
    if (!token) return;
    const id = window.setInterval(() => {
      const rt = refreshTokenRef.current;
      if (!rt) return;
      api
        .refresh(rt)
        .then(persist)
        .catch(() => logout());
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [token, persist, logout]);

  const login = useCallback(
    async (payload: LoginPayload) => persist(await api.login(payload)),
    [persist],
  );

  const signup = useCallback(
    async (payload: SignupPayload) => persist(await api.signup(payload)),
    [persist],
  );

  const value = useMemo<AuthState>(
    () => ({ user, token, loading, login, signup, logout }),
    [user, token, loading, login, signup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
