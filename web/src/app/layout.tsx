import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "@/lib/providers";
import { currentLocale, siteMetadata } from "@/lib/i18n/server";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  return { ...(await siteMetadata()), referrer: "no-referrer" };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await currentLocale();
  return (
    <html lang={locale}>
      <body>
        <Providers initialLocale={locale}>{children}</Providers>
      </body>
    </html>
  );
}
