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
        <span className="flex items-center gap-2 text-[15px] font-medium">
          <Radar className="size-4 text-primary" strokeWidth={1.5} />
          WebMonitor
        </span>
        <div className="space-y-1.5">
          <h1 className="text-[1.375rem] font-medium">{t("common.notFound.title")}</h1>
          <p className="meta leading-5">{t("common.notFound.body")}</p>
        </div>
        <Link
          href="/app"
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-input bg-card px-3.5 text-[13px] font-medium transition-colors duration-150 hover:bg-muted"
        >
          <ArrowLeft className="size-4" strokeWidth={1.5} />
          {t("common.notFound.back")}
        </Link>
      </div>
    </main>
  );
}
