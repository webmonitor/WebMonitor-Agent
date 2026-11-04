"use client";

import Link from "next/link";
import { ArrowRight, History, MailCheck, Radar, Settings2, Users } from "lucide-react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useI18n } from "@/lib/i18n";

const stepItems = [
  { id: "link", title: "public.steps.link.title", body: "public.steps.link.body" },
  { id: "preview", title: "public.steps.preview.title", body: "public.steps.preview.body" },
  { id: "notify", title: "public.steps.notify.title", body: "public.steps.notify.body" },
] as const;

const featureItems = [
  { id: "history", icon: History, title: "public.features.history.title", body: "public.features.history.body" },
  { id: "email", icon: MailCheck, title: "public.features.email.title", body: "public.features.email.body" },
  { id: "recipients", icon: Users, title: "public.features.recipients.title", body: "public.features.recipients.body" },
  { id: "control", icon: Settings2, title: "public.features.control.title", body: "public.features.control.body" },
] as const;

/**
 * The hero shows the one artifact this product produces: a change record.
 * A watched list is compared by business key, so the mail carries the rows that
 * appeared, not a second copy of the whole list. It sits on the dark surface
 * because it is machine output, not page copy.
 */
function ChangeRecord() {
  const { t } = useI18n();
  return (
    <figure className="w-full overflow-hidden rounded-xl bg-surface-dark p-6 text-on-dark sm:p-8">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[12px] font-medium uppercase tracking-[0.12em] text-on-dark-soft">
          {t("public.sample.title")}
        </span>
        <span className="text-[12px] text-on-dark-soft">{t("public.sample.badge")}</span>
      </div>

      <div className="mt-4 space-y-1">
        <p className="text-[16px] font-medium text-on-dark">{t("public.sample.product")}</p>
        <p className="num text-[12px] text-on-dark-soft">{t("public.sample.url")}</p>
      </div>

      <div className="mt-6 flex items-baseline gap-2 border-t border-on-dark/10 pt-5">
        <span className="num text-[14px] text-on-dark-soft line-through decoration-on-dark-soft/50">
          {t("public.sample.previousCount")}
        </span>
        <ArrowRight className="size-3.5 text-on-dark-soft" strokeWidth={1.5} />
        <span className="num text-[16px] font-medium text-on-dark">{t("public.sample.currentCount")}</span>
      </div>

      <div className="mt-4 rounded-lg bg-surface-dark-elevated px-4 py-3">
        <p className="flex items-center gap-1.5 text-[12px] font-medium uppercase tracking-[0.12em] text-on-dark-soft">
          <span aria-hidden className="text-accent-teal">+</span>
          {t("public.sample.added")}
        </p>
        <p className="mt-1.5 text-[14px] font-medium text-on-dark">{t("public.sample.addedTitle")}</p>
        <p className="num mt-1 text-[12px] text-on-dark-soft">{t("public.sample.addedMeta")}</p>
      </div>

      <figcaption className="mt-5 border-t border-on-dark/10 pt-4 text-[13px] leading-5 text-on-dark-soft">
        {t("public.sample.schedule")}
      </figcaption>
    </figure>
  );
}

export default function LandingPage() {
  const { t } = useI18n();

  return (
    <div className="min-h-dvh bg-canvas">
      <header className="mx-auto flex min-h-16 w-full max-w-[76rem] flex-wrap items-center gap-x-4 gap-y-1 px-6 py-3 sm:px-10">
        <span className="flex items-center gap-2.5 font-display text-[20px] leading-none tracking-[-0.02em] text-ink">
          <Radar className="size-[18px] text-primary" strokeWidth={1.5} />
          WebMonitor
        </span>
        <div className="ml-auto flex items-center gap-3">
          <LanguageSwitcher />
          <Link
            className="flex h-9 shrink-0 items-center gap-1.5 whitespace-nowrap text-[14px] font-medium text-ink transition-colors hover:text-primary-active"
            href="/app"
          >
            {t("public.nav.workspace")}
            <ArrowRight className="size-4" strokeWidth={1.5} />
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[76rem] px-6 sm:px-10">
        {/* First screen: copy on the left, the change record on the right. */}
        <section className="grid items-center gap-12 py-16 xl:min-h-[36rem] xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] xl:gap-16 xl:py-24">
          <div>
            <h1 className="display-xl">
              {t("public.hero.titleLine1")}
              <br />
              {t("public.hero.titleLine2")}
            </h1>
            <p className="t-body mt-6 max-w-[30rem] text-body">{t("public.hero.body")}</p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                className="inline-flex h-11 items-center gap-2 rounded-md bg-primary px-6 text-[14px] font-medium text-primary-foreground transition-colors duration-150 hover:bg-primary-active"
                href="/app"
              >
                {t("public.hero.cta")}
                <ArrowRight className="size-4" strokeWidth={1.5} />
              </Link>
              <Link
                className="inline-flex h-11 items-center rounded-md border border-input bg-canvas px-6 text-[14px] font-medium text-ink transition-colors duration-150 hover:bg-surface-card"
                href="#how-it-works"
              >
                {t("public.hero.secondaryCta")}
              </Link>
            </div>
            <p className="t-caption mt-5 text-muted-soft">{t("public.hero.note")}</p>
          </div>

          <ChangeRecord />
        </section>

        <section id="how-it-works" className="scroll-mt-6 border-t border-hairline py-24 sm:py-28">
          <h2 className="display-md">{t("public.steps.title")}</h2>
          <ol className="mt-10 grid gap-x-10 gap-y-8 sm:grid-cols-3">
            {stepItems.map((step, index) => (
              <li key={step.id} className="border-t border-hairline pt-5">
                <span className="num text-[13px] text-muted-soft">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <p className="t-title mt-3">{t(step.title)}</p>
                <p className="t-body-sm mt-2 text-muted-foreground">{t(step.body)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t border-hairline py-24 sm:py-28">
          <h2 className="display-md">{t("public.features.title")}</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2">
            {featureItems.map(({ id, icon: Icon, title, body }) => (
              <div key={id} className="rounded-lg bg-card p-8">
                <Icon className="size-5 text-ink" strokeWidth={1.5} />
                <h3 className="t-title mt-4">{t(title)}</h3>
                <p className="t-body-sm mt-2 text-muted-foreground">{t(body)}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="mt-24 bg-surface-dark">
        <div className="mx-auto flex w-full max-w-[76rem] flex-wrap items-center justify-between gap-3 px-6 py-16 text-on-dark-soft sm:px-10">
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-2.5 font-display text-[20px] tracking-[-0.02em] text-on-dark">
              <Radar className="size-[18px] text-primary" strokeWidth={1.5} />
              WebMonitor
            </span>
            <span className="t-body-sm">{t("public.footer.tagline")}</span>
          </div>
          <Link
            href="/app"
            className="text-[14px] text-on-dark underline-offset-4 hover:underline"
          >
            {t("public.nav.workspace")}
          </Link>
        </div>
      </footer>
    </div>
  );
}
