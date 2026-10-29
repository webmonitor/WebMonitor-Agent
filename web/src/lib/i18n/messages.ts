import { en as activityEn, zh as activityZh } from "./activity";
import { en as chatEn, zh as chatZh } from "./chat";
import { en as commonEn, zh as commonZh } from "./common";
import { en as monitorEn, zh as monitorZh } from "./monitors";
import { en as publicEn, zh as publicZh } from "./public";

export type Locale = "en" | "zh-CN";

export const LOCALE_COOKIE = "wm_locale";

export const en = {
  ...commonEn,
  ...publicEn,
  ...chatEn,
  ...monitorEn,
  ...activityEn,
};

export const zh = {
  ...commonZh,
  ...publicZh,
  ...chatZh,
  ...monitorZh,
  ...activityZh,
} as Record<keyof typeof en, string>;

export type MessageKey = keyof typeof en;

export const messages: Record<Locale, Record<MessageKey, string>> = { en, "zh-CN": zh };

export function isLocale(value: string | null | undefined): value is Locale {
  return value === "en" || value === "zh-CN";
}

export function translate(
  locale: Locale,
  key: MessageKey,
  values?: Record<string, string | number>,
): string {
  const template = messages[locale][key] ?? messages.en[key] ?? key;
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}
