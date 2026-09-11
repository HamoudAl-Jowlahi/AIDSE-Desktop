"use client";
/**
 * AIDSE Platform — Auth State Management
 * Manages session: access token in memory + current user cached in React context.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  auth as authApi,
  clearTokens,
  setAccessToken,
  type UserOut,
} from "./api";
import { setSessionNotice } from "./session-notice";

// ── Types ──────────────────────────────────────────────────────────────────

interface AuthState {
  user: UserOut | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

// ── Context ───────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me);
    } catch {
      setUser(null);
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login(email, password);
    setAccessToken(tokens.access_token);
    // Store refresh token in cookie (httpOnly set via API route in production)
    document.cookie = `refresh_token=${tokens.refresh_token}; path=/; SameSite=Strict`;
    const me = await authApi.me();
    setUser(me);
  }, []);

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      const tokens = await authApi.register(name, email, password);
      setAccessToken(tokens.access_token);
      document.cookie = `refresh_token=${tokens.refresh_token}; path=/; SameSite=Strict`;
      const me = await authApi.me();
      setUser(me);
    },
    []
  );

  const logout = useCallback(() => {
    clearTokens();
    document.cookie = "refresh_token=; path=/; expires=Thu, 01 Jan 1970 00:00:01 GMT";
    setUser(null);
    setSessionNotice("logged_out");
    window.location.href = "/login";
  }, []);

  // On mount: restore session by exchanging refresh token cookie → access token → /me
  useEffect(() => {
    const cookieRefresh = document.cookie
      .split("; ")
      .find((c) => c.startsWith("refresh_token="))
      ?.split("=")[1];

const LOCAL_DESKTOP_USER: UserOut = {
  id: "local-user-id",
  email: "local@aidse.internal",
  name: "AIDSE Analyst",
  role: "admin",
  is_active: true,
  created_at: new Date().toISOString(),
  last_login_at: null,
};

    if (!cookieRefresh) {
      setUser(LOCAL_DESKTOP_USER);
      setIsLoading(false);
      return;
    }

    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8010/api/v1";
    fetch(`${apiBase}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: cookieRefresh }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((data: { access_token: string }) => {
        setAccessToken(data.access_token);
        return refreshUser();
      })
      .catch(() => {
        // Refresh token expired or invalid — clear the stale cookie and let
        // the login page explain why the user was signed out.
        document.cookie = "refresh_token=; path=/; expires=Thu, 01 Jan 1970 00:00:01 GMT";
        setSessionNotice("expired");
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, [refreshUser]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: user !== null,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
