"use client";

import Link from "next/link";
import { ArrowRight, History, MailCheck, Radar, Settings2, Users } from "lucide-react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useI18n } from "@/lib/i18n";

const exampleItems = [
  { id: "price", title: "public.examples.price.title", detail: "public.examples.price.detail" },
  { id: "restock", title: "public.examples.restock.title", detail: "public.examples.restock.detail" },
  {
    id: "announcement",
    title: "public.examples.announcement.title",
    detail: "public.examples.announcement.detail",
  },
  {
    id: "deadline",
    title: "public.examples.deadline.title",
    detail: "public.examples.deadline.detail",
  },
] as const;

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
 * Old value struck, new value in the ink the product uses for "this changed".
 */
function ChangeRecord() {
  const { t } = useI18n();
  return (
    <figure className="surface w-full p-5 sm:p-6">
      <div className="flex items-baseline justify-between gap-3">
        <span className="label-line">{t("public.sample.title")}</span>
        <span className="text-[11px] text-muted-foreground">{t("public.sample.badge")}</span>
      </div>

      <div className="mt-3 space-y-0.5">
        <p className="text-[15px] font-medium">{t("public.sample.product")}</p>
        <p className="num text-[11px] text-muted-foreground">shop.example.com/product</p>
      </div>

      <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-end gap-3 border-t pt-4">
        <div>
          <p className="label-line">{t("public.sample.previous")}</p>
          <p className="num mt-1 text-[1.375rem] text-muted-foreground line-through decoration-muted-foreground/40">
            ¥128.50
          </p>
        </div>
        <ArrowRight className="mb-1.5 size-4 text-muted-foreground/60" strokeWidth={1.5} />
        <div className="text-right">
          <p className="label-line">{t("public.sample.current")}</p>
          <p className="num mt-1 text-[2rem] leading-none font-medium text-primary">¥99.00</p>
        </div>
      </div>

      <figcaption className="mt-4 border-t pt-3 text-xs leading-5 text-muted-foreground">
        {t("public.sample.schedule")}
      </figcaption>
    </figure>
  );
}

export default function LandingPage() {
  const { t } = useI18n();

  return (
    <div className="min-h-dvh bg-background">
      <header className="mx-auto flex h-16 w-full max-w-[76rem] items-center gap-4 px-6 sm:px-10">
        <span className="flex items-center gap-2 text-[15px] font-medium">
          <Radar className="size-4 text-primary" strokeWidth={1.5} />
          WebMonitor
        </span>
        <div className="ml-auto flex items-center gap-3 text-[13px]">
          <LanguageSwitcher />
          <Link
            className="flex h-9 items-center gap-1.5 font-medium text-foreground transition-colors duration-150 hover:text-primary"
            href="/app"
          >
            {t("public.nav.workspace")}
            <ArrowRight className="size-4" strokeWidth={1.5} />
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[76rem] px-6 sm:px-10">
        {/* First screen: copy on the left, the change record on the right. */}
        <section className="grid items-center gap-12 py-12 lg:min-h-[34rem] lg:grid-cols-[minmax(0,1fr)_minmax(0,32rem)] lg:gap-16 lg:py-16">
          <div className="max-w-[32rem]">
            <h1 className="text-[2rem] leading-[1.15] font-medium sm:text-[3rem] sm:leading-[1.08]">
              {t("public.hero.titleLine1")}
              <br />
              {t("public.hero.titleLine2")}
            </h1>
            <p className="mt-6 max-w-[30rem] text-[15px] leading-7 text-muted-foreground">
              {t("public.hero.body")}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                className="flex h-11 items-center gap-1.5 rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors duration-150 hover:bg-[var(--primary-hover)]"
                href="/app"
              >
                {t("public.hero.cta")}
                <ArrowRight className="size-4" strokeWidth={1.5} />
              </Link>
              <Link
                className="flex h-11 items-center rounded-lg border border-input bg-card px-5 text-sm transition-colors duration-150 hover:bg-muted"
                href="#how-it-works"
              >
                {t("public.hero.secondaryCta")}
              </Link>
            </div>
            <p className="mt-5 text-xs leading-5 text-muted-foreground">{t("public.hero.note")}</p>
          </div>

          <ChangeRecord />
        </section>

        <section className="border-t py-16 sm:py-20">
          <h2 className="text-[1.0625rem] font-medium">{t("public.examples.title")}</h2>
          <ul className="mt-6 divide-y">
            {exampleItems.map((example) => (
              <li key={example.id} className="grid gap-1 py-4 sm:grid-cols-[10rem_minmax(0,34rem)] sm:gap-6">
                <h3 className="text-[14px] font-medium">{t(example.title)}</h3>
                <p className="max-w-[38rem] text-[13px] leading-6 text-muted-foreground">
                  {t(example.detail)}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <section id="how-it-works" className="scroll-mt-6 border-t py-16 sm:py-20">
          <h2 className="text-[1.0625rem] font-medium">{t("public.steps.title")}</h2>
          <ol className="mt-6 grid gap-8 sm:grid-cols-3 sm:gap-10">
            {stepItems.map((step, index) => (
              <li key={step.id} className="border-t pt-3">
                <span className="num text-[11px] text-muted-foreground">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <p className="mt-2 text-[14px] font-medium">{t(step.title)}</p>
                <p className="mt-1.5 text-[13px] leading-6 text-muted-foreground">{t(step.body)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t py-16 sm:py-20">
          <h2 className="max-w-[34rem] text-[1.0625rem] font-medium">{t("public.features.title")}</h2>
          <div className="mt-6 grid gap-x-10 gap-y-6 sm:grid-cols-2">
            {featureItems.map(({ id, icon: Icon, title, body }) => (
              <div key={id} className="flex gap-3">
                <Icon className="mt-0.5 size-4 text-muted-foreground" strokeWidth={1.5} />
                <div className="min-w-0">
                  <h3 className="text-[14px] font-medium">{t(title)}</h3>
                  <p className="mt-1 max-w-[30rem] text-[13px] leading-6 text-muted-foreground">{t(body)}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="mx-auto flex w-full max-w-[76rem] flex-wrap items-center justify-between gap-2 border-t px-6 py-5 text-xs text-muted-foreground sm:px-10">
        <span>{t("public.footer.tagline")}</span>
      </footer>
    </div>
  );
}
