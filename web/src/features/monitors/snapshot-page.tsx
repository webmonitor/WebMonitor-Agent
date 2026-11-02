"use client";
import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { PageBody, PageHeader } from "@/components/page-header";
import { EvidenceLinks } from "@/features/monitors/evidence-links";
import { FieldValues } from "@/features/monitors/field-values";
import { useMonitor, useSnapshot } from "@/lib/api/hooks";
import { parseSpec } from "@/lib/api/preview";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

/** One check, as it was stored: every extracted value, coverage and evidence. */
export function SnapshotPage({
  monitorId,
  snapshotId,
}: {
  monitorId: string;
  snapshotId: string;
}) {
  const { t } = useI18n();
  const { coverageLabel, fieldLabels, formatDateTime, formatTime } = useFormat();
  const snapshot = useSnapshot(snapshotId);
  const monitor = useMonitor(monitorId);

  if (snapshot.isPending || monitor.isPending) {
    return (
      <div className="grid h-full place-items-center">
        <p className="meta">{t("monitors.loadingShort")}</p>
      </div>
    );
  }
  if (snapshot.error || !snapshot.data) {
    return (
      <div className="grid h-full place-items-center px-6 text-center">
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("monitors.snapshot.notFound")}</p>
          <Link className="text-sm text-primary underline-offset-2 hover:underline"
            href={`/app/monitors/${monitorId}`}>
            {t("monitors.snapshot.back")}
          </Link>
        </div>
      </div>
    );
  }

  const row = snapshot.data;
  const spec = parseSpec(monitor.data?.spec);
  const labels = fieldLabels(spec?.fields ?? []);
  const coverage = row.coverage as { scope?: string; description?: string };

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <Link
          href={`/app/monitors/${monitorId}`}
          className="mb-4 inline-flex items-center gap-1 text-[12px] text-muted-foreground transition-colors duration-150 hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" strokeWidth={1.5} />
          {monitor.data?.name ?? t("monitors.snapshot.back")}
        </Link>
        <PageHeader
          title={t("monitors.snapshot.title")}
          description={`${formatDateTime(row.collected_at)} · ${t("monitors.snapshot.description")}`}
        />

        <dl className="mb-8 grid overflow-hidden rounded-[0.875rem] border bg-card sm:grid-cols-3 sm:divide-x">
          <div className="border-b px-4 py-3 last:border-b-0 sm:border-b-0">
            <dt className="label-line">{t("monitors.snapshot.collectedAt")}</dt>
            <dd className="num mt-1 text-[13px]">{formatTime(row.collected_at)}</dd>
          </div>
          <div className="border-b px-4 py-3 last:border-b-0 sm:border-b-0">
            <dt className="label-line">{t("monitors.config.version")}</dt>
            <dd className="num mt-1 text-[13px]">
              {t("monitors.config.versionValue", { version: row.spec_version })}
            </dd>
          </div>
          <div className="px-4 py-3">
            <dt className="label-line">{t("monitors.config.coverage")}</dt>
            <dd className="mt-1 text-[13px]">{coverageLabel(coverage.scope)}</dd>
          </div>
        </dl>

        {coverage.description && <p className="meta mb-6 leading-5">{coverage.description}</p>}

        <section className="surface">
          <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
            <h2 className="section-title">{t("monitors.snapshot.values")}</h2>
            <a
              href={row.final_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex max-w-full items-center gap-1 truncate text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              {row.final_url}
              <ExternalLink className="size-3 shrink-0" strokeWidth={1.5} />
            </a>
          </header>
          <div className="px-4 py-2">
            <FieldValues values={row.extracted_data} labels={labels} />
          </div>
          {row.evidence_refs.length > 0 && (
            <div className="flex flex-wrap gap-3 border-t px-4 py-2.5">
              <EvidenceLinks snapshotId={row.id} references={row.evidence_refs} full />
            </div>
          )}
        </section>
      </PageBody>
    </div>
  );
}
