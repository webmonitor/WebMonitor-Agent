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

function hostOf(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.host + (parsed.pathname === "/" ? "" : parsed.pathname);
  } catch {
    return url;
  }
}

function FieldValues({ values, labels }: { values: Record<string, unknown>; labels: Record<string, string> }) {
  const { t } = useI18n();
  const { formatValue } = useFormat();
  const entries = Object.entries(values);
  if (entries.length === 0) return <p className="meta">{t("monitors.content.noFields")}</p>;
  return (
    <ul className="space-y-2">
      {entries.map(([name, value]) => (
        <li key={name} className="text-[13px]">
          <p className="meta">{labels[name] ?? name}</p>
          <p className="break-words font-medium tabular-nums">{formatValue(value)}</p>
        </li>
      ))}
    </ul>
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
  const events = useEvents();
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
              <ExternalLink className="size-3 shrink-0" />
            </a>
          }
          actions={
            <>
              {row.status === "active" ? (
                <Button variant="outline" size="sm" onClick={() => void pause.mutateAsync(row.id)} disabled={busy}>
                  <Pause className="size-3.5" />
                  {t("monitors.action.pause")}
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => void resume.mutateAsync(row.id)} disabled={busy}>
                  <Play className="size-3.5" />
                  {t("monitors.action.resume")}
                </Button>
              )}
              <Button size="sm" onClick={() => void run.mutateAsync(row.id)} disabled={busy}>
                <Zap className="size-3.5" />
                {t("monitors.action.runNow")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground"
                disabled={derive.isPending}
                onClick={async () => {
                  const result = await derive.mutateAsync(row.id);
                  router.push(`/app?conversation=${result.conversation_id}`);
                }}
              >
                <Settings2 className="size-3.5" />
                {t("monitors.action.editSettings")}
              </Button>
            </>
          }
        >
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Badge tone={row.status === "active" ? "success" : "neutral"}>{statusLabel(row.status)}</Badge>
            {row.health_status === "failed" && <Badge tone="error">{t("monitors.badge.lastCheckFailed")}</Badge>}
            {row.baseline_status !== "ready" && <Badge tone="warning">{t("monitors.badge.baselinePending")}</Badge>}
          </div>
        </PageHeader>

        <dl className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.label} className="surface-pad">
              <dt className="meta">{stat.label}</dt>
              <dd className="mt-0.5 truncate text-[13px] font-medium tabular-nums">{stat.value}</dd>
            </div>
          ))}
        </dl>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <section className="space-y-2">
            <h2 className="section-title">{t("monitors.jobs.title")}</h2>
            {jobs.isPending && <p className="meta">{t("monitors.loadingShort")}</p>}
            {!jobs.isPending && (jobs.data?.items.length ?? 0) === 0 && (
              <EmptyState
                title={t("monitors.jobs.emptyTitle")}
                description={t("monitors.jobs.emptyBody")}
              />
            )}
            <ul className="space-y-1.5">
              {(jobs.data?.items ?? []).map((job) => (
                <li key={job.id}>
                  <button
                    className="surface flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:border-ring/40"
                    onClick={() => setOpenJob(job.id)}
                  >
                    <span className="w-[4.5rem] shrink-0 text-[13px] tabular-nums">
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
                      <span className="meta shrink-0 tabular-nums">
                        {t("monitors.job.attempts", { count: job.attempt_count })}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <aside className="space-y-4">
            <section className="surface-pad space-y-3">
              <div className="flex items-baseline justify-between">
                <h2 className="section-title">{t("monitors.content.title")}</h2>
                <span className="meta">{row.baseline ? formatTime(row.baseline.collected_at) : "—"}</span>
              </div>
              {row.baseline ? (
                <FieldValues values={values} labels={labels} />
              ) : (
                <p className="meta">{t("monitors.content.empty")}</p>
              )}
              {row.baseline && row.baseline.evidence_refs.length > 0 && (
                <div className="flex flex-wrap gap-1.5 border-t pt-3">
                  {row.baseline.evidence_refs.map((reference, index) => (
                    <a
                      key={reference.sha256}
                      className="chip bg-muted text-[11px] text-muted-foreground hover:text-foreground"
                      href={`/api/v1/snapshots/${row.baseline?.id}/evidence/${index}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {reference.kind === "screenshot"
                        ? t("monitors.evidence.screenshot")
                        : t("monitors.evidence.archive")}
                      <span className="tabular-nums">{formatBytes(reference.size_bytes)}</span>
                    </a>
                  ))}
                </div>
              )}
            </section>

            <section className="space-y-2">
              <div className="flex items-baseline justify-between">
                <h2 className="section-title">{t("monitors.events.title")}</h2>
                <Link href="/app/events" className="text-xs text-primary underline-offset-2 hover:underline">
                  {t("monitors.events.all")}
                </Link>
              </div>
              {monitorEvents.length === 0 ? (
                <p className="meta">{t("monitors.events.empty")}</p>
              ) : (
                <ul className="space-y-2">
                  {monitorEvents.slice(0, 3).map((event) => (
                    <li key={event.id} className="surface space-y-1.5 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <Badge tone={event.type === "run_failed" ? "error" : event.type === "recovered" ? "success" : "brand"}>
                          {formatTime(event.created_at)}
                        </Badge>
                      </div>
                      <ChangeRows change={event.change} type={event.type} />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>
        </div>
      </PageBody>

      <Dialog open={Boolean(openJob)} onOpenChange={(value) => !value && setOpenJob(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-base">{t("monitors.dialog.title")}</DialogTitle>
          </DialogHeader>
          {detail.isPending && <p className="meta">{t("monitors.loadingShort")}</p>}
          {detail.data && (
            <div className="space-y-4 text-[13px]">
              <dl className="grid grid-cols-2 gap-3">
                <div>
                  <dt className="meta">{t("monitors.dialog.status")}</dt>
                  <dd>{statusLabel(detail.data.status)}</dd>
                </div>
                <div>
                  <dt className="meta">{t("monitors.dialog.startedAt")}</dt>
                  <dd>{formatDateTime(detail.data.created_at)}</dd>
                </div>
                <div>
                  <dt className="meta">{t("monitors.dialog.attempts")}</dt>
                  <dd className="tabular-nums">{detail.data.attempt_count}</dd>
                </div>
                <div>
                  <dt className="meta">{t("monitors.dialog.finishedAt")}</dt>
                  <dd>{formatDateTime(detail.data.finished_at)}</dd>
                </div>
              </dl>

              {detail.data.error_code && (
                <p className="flex items-start gap-2 rounded-lg border border-error/25 bg-error/5 px-3 py-2 text-xs text-error">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  {errorText(detail.data.error_code)}
                </p>
              )}

              {detail.data.snapshot && (
                <div className="space-y-2">
                  <h3 className="meta">{t("monitors.dialog.captured")}</h3>
                  <FieldValues values={detail.data.snapshot.extracted_data} labels={labels} />
                  {detail.data.snapshot.evidence_refs.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {detail.data.snapshot.evidence_refs.map((reference, index) => (
                        <a
                          key={reference.sha256}
                          className="chip bg-muted text-[11px] text-muted-foreground hover:text-foreground"
                          href={`/api/v1/snapshots/${detail.data?.snapshot?.id}/evidence/${index}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {reference.kind === "screenshot"
                            ? t("monitors.evidence.screenshotFull")
                            : t("monitors.evidence.archive")}
                          <span className="tabular-nums">{formatBytes(reference.size_bytes)}</span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {detail.data.attempts.length > 1 && (
                <div className="space-y-1.5">
                  <h3 className="meta">{t("monitors.dialog.attemptLog")}</h3>
                  <ul className="divide-y rounded-lg border">
                    {detail.data.attempts.map((attempt) => (
                      <li key={attempt.number} className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs">
                        <span>
                          {t("monitors.dialog.attemptRow", {
                            number: attempt.number,
                            status: statusLabel(attempt.status),
                          })}
                        </span>
                        <span className="text-muted-foreground tabular-nums">
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
