"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, clearCsrfToken, clearSessionClient, safeReturnTo } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { I18nProvider } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n/messages";

type AuthProfile = components["schemas"]["Member"];
type AuthContextValue = {
  user: AuthProfile | undefined;
  isPending: boolean;
  error: Error | null;
  refresh: () => Promise<unknown>;
  prepareAuthentication: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = React.createContext<AuthContextValue | null>(null);

function redirectToLogin() {
  const returnTo = safeReturnTo(
    window.location.pathname + window.location.search + window.location.hash,
  );
  window.location.assign(`/login?returnTo=${encodeURIComponent(returnTo)}`);
}

function AuthProvider({ children }: { children: React.ReactNode }) {
  const cache = useQueryClient();
  const hadUser = React.useRef(false);
  const sessionUserId = React.useRef<string | null>(null);
  const query = useQuery({
    queryKey: ["auth"],
    queryFn: async () => {
      try {
        return await api<AuthProfile>("/auth/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 30_000,
  });

  React.useEffect(() => {
    if (query.data) {
      const previousId = sessionUserId.current;
      sessionUserId.current = query.data.id;
      hadUser.current = true;
      if (previousId && previousId !== query.data.id) {
        // A direct A → B account switch must not leave A's protected queries alive.
        clearCsrfToken();
        cache.clear();
        window.location.reload();
      }
      return;
    }
    if (query.data === null && hadUser.current) {
      hadUser.current = false;
      sessionUserId.current = null;
      clearCsrfToken();
      cache.clear();
      redirectToLogin();
    }
  }, [query.data, cache]);

  React.useEffect(() => {
    const clear = () => {
      cache.clear();
      if (hadUser.current) {
        hadUser.current = false;
        sessionUserId.current = null;
        redirectToLogin();
      }
    };
    window.addEventListener("wm:session-ended", clear);
    return () => window.removeEventListener("wm:session-ended", clear);
  }, [cache]);

  async function prepareAuthentication() {
    // Cancel in-flight A requests before the cookie changes, then remove all
    // protected data. The full navigation after authentication isolates B too.
    hadUser.current = false;
    sessionUserId.current = null;
    await cache.cancelQueries();
    cache.clear();
    clearCsrfToken();
    cache.setQueryData(["auth"], null);
  }

  async function logout() {
    await api<void>("/auth/logout", { method: "POST" });
    hadUser.current = false;
    sessionUserId.current = null;
    clearSessionClient();
    cache.clear();
    window.location.assign("/login");
  }

  const switchingAccount = Boolean(
    sessionUserId.current && query.data?.id && sessionUserId.current !== query.data.id,
  );
  const value: AuthContextValue = {
    user: query.data ?? undefined,
    isPending: query.isPending,
    error: query.error,
    refresh: query.refetch,
    prepareAuthentication,
    logout,
  };
  return <AuthContext.Provider value={value}>{switchingAccount ? null : children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("AuthProvider missing");
  return context;
}

export function Providers({ children, initialLocale }: { children: React.ReactNode; initialLocale: Locale }) {
  const [client] = React.useState(() => new QueryClient({
    defaultOptions: {
      queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 10_000 },
    },
  }));
  return (
    <I18nProvider initialLocale={initialLocale}>
      <QueryClientProvider client={client}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    </I18nProvider>
  );
}
