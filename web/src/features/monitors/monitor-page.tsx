"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertTriangle, ExternalLink, Pause, Play, Settings2, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/empty-state";
import { PageBody, PageHeader } from "@/components/page-header";
import {
  useDeriveDraft,
  useEvents,
  useJobDetail,
  useMonitor,
  useMonitorJobs,
  usePauseMonitor,
  useResumeMonitor,
  useRunNow,
} from "@/lib/api/hooks";
import { parseSpec } from "@/lib/api/preview";
import { formatBytes, useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { ChangeRows } from "@/features/events/event-card";
import { ListPagination } from "@/components/list-pagination";

function hostOf(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.host + (parsed.pathname === "/" ? "" : parsed.pathname);
  } catch {
    return url;
  }
}

/** Collected fields as a ruled ledger: label in ink-grey, value in tabular mono. */
function FieldValues({ values, labels }: { values: Record<string, unknown>; labels: Record<string, string> }) {
  const { t } = useI18n();
  const { formatValue } = useFormat();
  const entries = Object.entries(values);
  if (entries.length === 0) return <p className="meta">{t("monitors.content.noFields")}</p>;
  return (
    <dl className="divide-y">
      {entries.map(([name, value]) => (
        <div key={name} className="flex items-baseline justify-between gap-3 py-2">
          <dt className="shrink-0 text-[12px] text-muted-foreground">{labels[name] ?? name}</dt>
          <dd className="num min-w-0 truncate text-right text-[13px]">{formatValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function MonitorPage({ monitorId }: { monitorId: string }) {
  const { t } = useI18n();
  const {
    errorText,
    eventLabel,
    fieldLabels,
    formatClock,
    formatDateTime,
    formatInterval,
    formatMode,
    formatTime,
    statusLabel,
  } = useFormat();
  const monitor = useMonitor(monitorId);
  const jobs = useMonitorJobs(monitorId, 10);
  const events = useEvents(monitorId);
  const pause = usePauseMonitor();
  const resume = useResumeMonitor();
  const run = useRunNow();
  const derive = useDeriveDraft();
  const router = useRouter();
  const [openJob, setOpenJob] = useState<string | null>(null);
  const detail = useJobDetail(openJob);

  if (monitor.isPending) {
    return (
      <div className="grid h-full place-items-center">
        <p className="meta">{t("monitors.loading")}</p>
      </div>
    );
  }
  if (monitor.error || !monitor.data) {
    return (
      <div className="grid h-full place-items-center px-6 text-center">
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("monitors.notFound.title")}</p>
          <p className="meta">{t("monitors.notFound.body")}</p>
          <Link className="text-sm text-primary underline-offset-2 hover:underline" href="/app">
            {t("monitors.backToChat")}
          </Link>
        </div>
      </div>
    );
  }

  const row = monitor.data;
  const spec = parseSpec(row.spec);
  const fields = spec?.fields ?? [];
  const labels = fieldLabels(fields);
  const busy = pause.isPending || resume.isPending || run.isPending;
  const monitorEvents = (events.data?.items ?? []).filter((event) => event.monitor_id === row.id);
  const eventByJob = new Map(monitorEvents.map((event) => [event.job_id, event.type]));
  const values = row.baseline?.extracted_data ?? {};
  const jobItems = jobs.data?.items ?? [];

  const stats = [
    { label: t("monitors.stat.lastCheck"), value: formatTime(row.last_success_at) },
    {
      label: t("monitors.stat.nextCheck"),
      value: row.status === "active" ? formatTime(row.next_run_at) : t("monitors.paused"),
    },
    { label: t("monitors.stat.interval"), value: formatInterval(row.interval_seconds) },
    { label: t("monitors.stat.mode"), value: formatMode(row.collection_mode) },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title={row.name}
          description={
            <a
              className="inline-flex max-w-full items-center gap-1 truncate text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              href={row.url}
              target="_blank"
              rel="noreferrer"
            >
              {hostOf(row.url)}
              <ExternalLink className="size-3.5 shrink-0" strokeWidth={1.5} />
            </a>
          }
          actions={
            <>
              {row.status === "active" ? (
                <Button variant="outline" size="sm" onClick={() => pause.mutate(row.id)} disabled={busy}>
                  <Pause className="size-3.5" strokeWidth={1.5} />
                  {t("monitors.action.pause")}
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => resume.mutate(row.id)} disabled={busy}>
                  <Play className="size-3.5" strokeWidth={1.5} />
                  {t("monitors.action.resume")}
                </Button>
              )}
              <Button size="sm" onClick={() => run.mutate(row.id)} disabled={busy || row.status !== "active"}>
                <Zap className="size-3.5" strokeWidth={1.5} />
                {t("monitors.action.runNow")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground"
                disabled={derive.isPending}
                onClick={() => derive.mutate(row.id, {
                  onSuccess: (result) => router.push(`/app?conversation=${result.conversation_id}`),
                })}
              >
                <Settings2 className="size-3.5" strokeWidth={1.5} />
                {t("monitors.action.editSettings")}
              </Button>
            </>
          }
        >
          <div className="flex flex-wrap items-center gap-2 pt-1.5">
            <Badge tone={row.status === "active" ? "success" : "neutral"}>{statusLabel(row.status)}</Badge>
            {row.health_status === "failed" && <Badge tone="error">{t("monitors.badge.lastCheckFailed")}</Badge>}
            {row.baseline_status !== "ready" && <Badge tone="warning">{t("monitors.badge.baselinePending")}</Badge>}
          </div>
        </PageHeader>
        {(pause.error || resume.error || run.error || derive.error) && (
          <p role="alert" className="mb-4 text-sm text-error">{errorText(pause.error || resume.error || run.error || derive.error)}</p>
        )}

        {/* Four figures on one ruled strip, not four cards. */}
        <dl className="mb-8 grid overflow-hidden rounded-[0.875rem] border bg-card sm:grid-cols-4 sm:divide-x">
          {stats.map((stat) => (
            <div key={stat.label} className="border-b px-4 py-3 last:border-b-0 sm:border-b-0">
              <dt className="label-line">{stat.label}</dt>
              <dd className="num mt-1 truncate text-[13px]">{stat.value}</dd>
            </div>
          ))}
        </dl>

        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="space-y-10">
            <section>
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <h2 className="section-title">{t("monitors.events.title")}</h2>
                <Link href="/app/events" className="text-[11px] text-primary underline-offset-2 hover:underline">
                  {t("monitors.events.all")}
                </Link>
              </div>
              {events.error && <p role="alert" className="text-xs text-error">{t("common.listError")}</p>}
              {!events.error && monitorEvents.length === 0 ? (
                <p className="meta">{t("monitors.events.empty")}</p>
              ) : (
                <>
                  {/* The newest change is the record this monitor exists to produce. */}
                  {monitorEvents[0] && (
                    <article className="surface mb-3">
                      <header className="flex items-center justify-between gap-2 border-b px-4 py-2.5">
                        <Badge
                          tone={
                            monitorEvents[0].type === "run_failed"
                              ? "error"
                              : monitorEvents[0].type === "recovered"
                                ? "success"
                                : "brand"
                          }
                        >
                          {eventLabel(monitorEvents[0].type)}
                        </Badge>
                        <span className="num text-[11px] text-muted-foreground">
                          {formatTime(monitorEvents[0].created_at)}
                        </span>
                      </header>
                      <div className="px-4 py-2">
                        <ChangeRows change={monitorEvents[0].change} type={monitorEvents[0].type} />
                      </div>
                    </article>
                  )}
                  <ul className="divide-y border-t">
                    {monitorEvents.slice(1, 4).map((event) => (
                      <li key={event.id} className="space-y-1.5 py-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <Badge tone={event.type === "run_failed" ? "error" : event.type === "recovered" ? "success" : "brand"}>
                            {eventLabel(event.type)}
                          </Badge>
                          <span className="num text-[11px] text-muted-foreground">{formatTime(event.created_at)}</span>
                        </div>
                        <ChangeRows change={event.change} type={event.type} />
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>

            <section>
              <h2 className="section-title mb-2">{t("monitors.jobs.title")}</h2>
              {jobs.isPending && <p className="meta">{t("monitors.loadingShort")}</p>}
              {!jobs.isPending && !jobs.error && jobItems.length === 0 && (
                <EmptyState
                  title={t("monitors.jobs.emptyTitle")}
                  description={t("monitors.jobs.emptyBody")}
                />
              )}
              <ul className="border-t">
                {jobItems.map((job) => (
                  <li key={job.id}>
                    <button
                      className="flex w-full items-center gap-3 border-b py-2.5 text-left transition-colors duration-150 hover:bg-muted/60"
                      onClick={() => setOpenJob(job.id)}
                    >
                      <span className="num w-[4.5rem] shrink-0 text-[12px] text-muted-foreground">
                        {formatClock(job.created_at)}
                      </span>
                      <Badge tone={job.status === "succeeded" ? "success" : job.status === "failed" ? "error" : "neutral"}>
                        {statusLabel(job.status)}
                      </Badge>
                      <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                        {job.error_code
                          ? errorText(job.error_code)
                          : eventByJob.has(job.id)
                            ? t("monitors.job.detected", { event: eventLabel(eventByJob.get(job.id)) })
                            : job.status === "succeeded"
                              ? t("monitors.job.saved")
                              : ""}
                      </span>
                      {job.attempt_count > 1 && (
                        <span className="num shrink-0 text-[11px] text-muted-foreground">
                          {t("monitors.job.attempts", { count: job.attempt_count })}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
              <ListPagination query={jobs} />
            </section>
          </div>

          <aside>
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <h2 className="section-title">{t("monitors.content.title")}</h2>
              <span className="num text-[11px] text-muted-foreground">
                {row.baseline ? formatTime(row.baseline.collected_at) : "—"}
              </span>
            </div>
            {row.baseline ? (
              <FieldValues values={values} labels={labels} />
            ) : (
              <p className="meta">{t("monitors.content.empty")}</p>
            )}
            {row.baseline && row.baseline.evidence_refs.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t pt-3">
                {row.baseline.evidence_refs.map((reference, index) => (
                  <a
                    key={reference.sha256}
                    className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground transition-colors duration-150 hover:text-foreground"
                    href={`/api/v1/snapshots/${row.baseline?.id}/evidence/${index}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {reference.kind === "screenshot"
                      ? t("monitors.evidence.screenshot")
                      : t("monitors.evidence.archive")}
                    <span className="num">{formatBytes(reference.size_bytes)}</span>
                  </a>
                ))}
              </div>
            )}
          </aside>
        </div>
      </PageBody>

      <Dialog open={Boolean(openJob)} onOpenChange={(value) => !value && setOpenJob(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-base">{t("monitors.dialog.title")}</DialogTitle>
          </DialogHeader>
          {detail.isPending && <p className="meta">{t("monitors.loadingShort")}</p>}
          {detail.error && <p role="alert" className="text-sm text-error">{errorText(detail.error)}</p>}
          {detail.data && (
            <div className="space-y-5 text-[13px]">
              <dl className="grid grid-cols-2 gap-3">
                <div>
                  <dt className="label-line">{t("monitors.dialog.status")}</dt>
                  <dd>{statusLabel(detail.data.status)}</dd>
                </div>
                <div>
                  <dt className="label-line">{t("monitors.dialog.startedAt")}</dt>
                  <dd className="num">{formatDateTime(detail.data.created_at)}</dd>
                </div>
                <div>
                  <dt className="label-line">{t("monitors.dialog.attempts")}</dt>
                  <dd className="num">{detail.data.attempt_count}</dd>
                </div>
                <div>
                  <dt className="label-line">{t("monitors.dialog.finishedAt")}</dt>
                  <dd className="num">{formatDateTime(detail.data.finished_at)}</dd>
                </div>
              </dl>

              {detail.data.error_code && (
                <p className="flex items-start gap-2 border-l-2 border-error/40 pl-2.5 text-xs leading-5 text-error">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.5} />
                  {errorText(detail.data.error_code)}
                </p>
              )}

              {detail.data.snapshot && (
                <div>
                  <h3 className="label-line mb-1.5">{t("monitors.dialog.captured")}</h3>
                  <FieldValues values={detail.data.snapshot.extracted_data} labels={labels} />
                  {detail.data.snapshot.evidence_refs.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
                      {detail.data.snapshot.evidence_refs.map((reference, index) => (
                        <a
                          key={reference.sha256}
                          className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground transition-colors duration-150 hover:text-foreground"
                          href={`/api/v1/snapshots/${detail.data?.snapshot?.id}/evidence/${index}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {reference.kind === "screenshot"
                            ? t("monitors.evidence.screenshotFull")
                            : t("monitors.evidence.archive")}
                          <span className="num">{formatBytes(reference.size_bytes)}</span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {detail.data.attempts.length > 1 && (
                <div>
                  <h3 className="label-line mb-1.5">{t("monitors.dialog.attemptLog")}</h3>
                  <ul className="divide-y border-t">
                    {detail.data.attempts.map((attempt) => (
                      <li key={attempt.number} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                        <span>
                          {t("monitors.dialog.attemptRow", {
                            number: attempt.number,
                            status: statusLabel(attempt.status),
                          })}
                        </span>
                        <span className="num text-muted-foreground">
                          {attempt.error_code ? errorText(attempt.error_code) : formatTime(attempt.finished_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
