import type { Metadata } from "next";
import { cookies } from "next/headers";
import { isLocale, LOCALE_COOKIE, translate, type Locale, type MessageKey } from "./messages";

export async function currentLocale(): Promise<Locale> {
  const value = (await cookies()).get(LOCALE_COOKIE)?.value;
  return isLocale(value) ? value : "zh-CN";
}

export async function localizedMetadata(key: MessageKey): Promise<Metadata> {
  return { title: translate(await currentLocale(), key) };
}

export async function siteMetadata(): Promise<Metadata> {
  const locale = await currentLocale();
  return {
    title: { default: translate(locale, "common.siteTitle"), template: "%s · WebMonitor" },
    description: translate(locale, "common.description"),
  };
}
