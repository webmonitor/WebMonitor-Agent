"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import {
  isLocale,
  LOCALE_COOKIE,
  translate,
  type Locale,
  type MessageKey,
} from "@/lib/i18n/messages";

type I18nValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey, values?: Record<string, string | number>) => string;
};

const I18nContext = React.createContext<I18nValue | null>(null);

const STORAGE_KEY = "wm-locale";

function persist(locale: Locale) {
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* Storage can be unavailable in private modes; the cookie still applies. */
  }
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
  document.documentElement.lang = locale;
}

function titleKey(pathname: string): MessageKey | null {
  if (pathname === "/") return "common.siteTitle";
  if (pathname.startsWith("/login")) return "common.title.login";
  if (pathname.startsWith("/register")) return "common.title.register";
  if (pathname.startsWith("/app/events")) return "common.title.events";
  if (pathname.startsWith("/app/notifications")) return "common.title.notifications";
  if (pathname.startsWith("/app/monitors/")) return "common.title.monitor";
  if (pathname.startsWith("/app")) return "common.title.workspace";
  return null;
}

export function I18nProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale;
  children: React.ReactNode;
}) {
  const [locale, setLocaleState] = React.useState<Locale>(initialLocale);
  const pathname = usePathname();

  React.useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      /* Ignore unavailable storage. */
    }
    if (isLocale(stored) && stored !== locale) {
      setLocaleState(stored);
      persist(stored);
    }
  }, [locale]);

  const setLocale = React.useCallback((next: Locale) => {
    setLocaleState(next);
    persist(next);
  }, []);

  React.useEffect(() => {
    document.documentElement.lang = locale;
    const key = titleKey(pathname);
    if (key) {
      document.title = translate(locale, key) + (key === "common.siteTitle" ? "" : " · WebMonitor");
    }
  }, [locale, pathname]);

  const value = React.useMemo<I18nValue>(
    () => ({
      locale,
      setLocale,
      t: (key, values) => translate(locale, key, values),
    }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const context = React.useContext(I18nContext);
  if (!context) throw new Error("I18nProvider missing");
  return context;
}
