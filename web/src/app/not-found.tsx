"use client";

import Link from "next/link";
import { ArrowLeft, Radar } from "lucide-react";
import { useI18n } from "@/lib/i18n";

/** A missed address is still a page of this product: same paper, same wordmark. */
export default function NotFound() {
  const { t } = useI18n();
  return (
    <main className="grid min-h-dvh place-items-center px-6">
      <div className="w-full max-w-[22rem] space-y-5">
        <span className="flex items-center gap-2.5 font-display text-[20px] leading-none tracking-[-0.02em] text-ink">
          <Radar className="size-[18px] text-primary" strokeWidth={1.5} />
          WebMonitor
        </span>
        <div className="space-y-1.5">
          <h1 className="display-md">{t("common.notFound.title")}</h1>
          <p className="t-body-sm text-muted-foreground">{t("common.notFound.body")}</p>
        </div>
        <Link
          href="/app"
          className="inline-flex h-10 items-center gap-1.5 rounded-md border border-input bg-canvas px-4 text-[14px] font-medium text-ink transition-colors hover:bg-surface-card"
        >
          <ArrowLeft className="size-4" strokeWidth={1.5} />
          {t("common.notFound.back")}
        </Link>
      </div>
    </main>
  );
}
