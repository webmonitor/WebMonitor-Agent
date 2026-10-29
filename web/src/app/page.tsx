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
  {
    id: "history",
    icon: History,
    title: "public.features.history.title",
    body: "public.features.history.body",
  },
  {
    id: "email",
    icon: MailCheck,
    title: "public.features.email.title",
    body: "public.features.email.body",
  },
  {
    id: "recipients",
    icon: Users,
    title: "public.features.recipients.title",
    body: "public.features.recipients.body",
  },
  {
    id: "control",
    icon: Settings2,
    title: "public.features.control.title",
    body: "public.features.control.body",
  },
] as const;

const samplePrices = [
  { id: "previous", label: "public.sample.previous", value: "¥128.50" },
  { id: "current", label: "public.sample.current", value: "¥99.00" },
] as const;

export default function LandingPage() {
  const { t } = useI18n();

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-5xl flex-col px-6 py-6">
      <nav aria-label={t("public.nav.aria")} className="flex flex-wrap items-center justify-between gap-2 sm:gap-4">
        <span className="flex items-center gap-2 text-[15px] font-semibold">
          <Radar className="size-5 text-primary" />
          WebMonitor
        </span>
        <div className="flex items-center gap-2 text-sm">
          <LanguageSwitcher />
          <Link className="rounded-lg px-3 py-1.5 text-muted-foreground hover:text-foreground" href="/login">
            {t("public.nav.login")}
          </Link>
          <Link
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 font-medium text-primary-foreground hover:opacity-90"
            href="/app"
          >
            {t("public.nav.workspace")}
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      </nav>

      <section className="grid gap-10 py-14 lg:grid-cols-[minmax(0,1fr)_21rem] lg:items-center lg:py-20">
        <div>
          <p className="text-xs font-medium tracking-wide text-primary">{t("public.hero.eyebrow")}</p>
          <h1 className="mt-2 max-w-xl text-[2.1rem] font-semibold leading-[1.25] tracking-tight sm:text-[2.5rem]">
            {t("public.hero.titleLine1")}
            <br />
            {t("public.hero.titleLine2")}
          </h1>
          <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            {t("public.hero.body")}
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90"
              href="/app"
            >
              {t("public.hero.cta")}
              <ArrowRight className="size-4" />
            </Link>
            <Link className="rounded-lg border bg-card px-4 py-2.5 text-sm hover:bg-muted" href="#how-it-works">
              {t("public.hero.secondaryCta")}
            </Link>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">{t("public.hero.note")}</p>
        </div>

        <div className="surface-pad space-y-5 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">{t("public.sample.title")}</p>
            <span className="chip border-success/30 bg-success/10 text-success">{t("public.sample.badge")}</span>
          </div>
          <div>
            <p className="text-[15px] font-medium">{t("public.sample.product")}</p>
            <p className="mt-1 text-xs text-muted-foreground">shop.example.com/product</p>
          </div>
          <dl className="grid grid-cols-2 gap-4">
            {samplePrices.map((price) => (
              <div key={price.id}>
                <dt className="text-xs text-muted-foreground">{t(price.label)}</dt>
                <dd className="mt-1 text-xl font-semibold tabular-nums">{price.value}</dd>
              </div>
            ))}
          </dl>
          <p className="border-t pt-3 text-xs leading-relaxed text-muted-foreground">
            {t("public.sample.schedule")}
          </p>
        </div>
      </section>

      <section className="border-t py-10">
        <h2 className="text-xl font-semibold">{t("public.examples.title")}</h2>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2">
          {exampleItems.map((example) => (
            <li key={example.id} className="surface space-y-2 p-5">
              <h3 className="text-[15px] font-medium">{t(example.title)}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">{t(example.detail)}</p>
            </li>
          ))}
        </ul>
      </section>

      <section id="how-it-works" className="scroll-mt-6 border-t py-10">
        <h2 className="text-xl font-semibold">{t("public.steps.title")}</h2>
        <ol className="mt-4 grid gap-6 sm:grid-cols-3">
          {stepItems.map((step, index) => (
            <li key={step.id} className="space-y-1.5">
              <span className="grid size-7 place-items-center rounded-full border text-xs font-semibold tabular-nums text-primary">
                {index + 1}
              </span>
              <p className="text-[15px] font-medium">{t(step.title)}</p>
              <p className="text-sm leading-relaxed text-muted-foreground">{t(step.body)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-t py-10">
        <h2 className="text-xl font-semibold">{t("public.features.title")}</h2>
        <div className="mt-5 grid gap-6 sm:grid-cols-2">
          {featureItems.map(({ id, icon: Icon, title, body }) => (
            <div key={id} className="flex gap-3">
              <Icon className="mt-0.5 size-4 shrink-0 text-primary" />
              <div>
                <h3 className="text-[15px] font-medium">{t(title)}</h3>
                <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{t(body)}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t py-4 text-xs text-muted-foreground">
        <span>{t("public.footer.tagline")}</span>
      </footer>
    </main>
  );
}
