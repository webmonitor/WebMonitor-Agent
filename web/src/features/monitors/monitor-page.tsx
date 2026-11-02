"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  AlertTriangle,
  Archive,
  ExternalLink,
  Pause,
  Pencil,
  Play,
  RefreshCw,
  RotateCcw,
  Settings2,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageBody, PageHeader } from "@/components/page-header";
import {
  useArchiveMonitor,
  useCancelJob,
  useDeriveDraft,
  useEvents,
  useJobDetail,
  useMonitor,
  useMonitorJobs,
  usePauseMonitor,
  useRenameMonitor,
  useRestoreMonitor,
  useResumeMonitor,
  useRunNow,
  useSnapshots,
} from "@/lib/api/hooks";
import { parseSpec } from "@/lib/api/preview";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { ChangeRows } from "@/features/events/event-card";
import { EvidenceLinks } from "@/features/monitors/evidence-links";
import { FieldValues } from "@/features/monitors/field-values";
import { MonitorConfig } from "@/features/monitors/monitor-config";
import { MonitorEditor } from "@/features/monitors/monitor-editor";
import { ListPagination } from "@/components/list-pagination";

function hostOf(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.host + (parsed.pathname === "/" ? "" : parsed.pathname);
  } catch {
    return url;
  }
}

export function MonitorPage({
  monitorId,
  initialJob,
}: {
  monitorId: string;
  initialJob?: string | null;
}) {
  const { t } = useI18n();
  const {
    coverageLabel,
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
  const snapshots = useSnapshots(monitorId);
  const events = useEvents(monitorId);
  const pause = usePauseMonitor();
  const resume = useResumeMonitor();
  const run = useRunNow();
  const derive = useDeriveDraft();
  const rename = useRenameMonitor();
  const archive = useArchiveMonitor();
  const restore = useRestoreMonitor();
  const cancelJob = useCancelJob();
  const router = useRouter();
  const [openJob, setOpenJob] = useState<string | null>(initialJob ?? null);
  const [editing, setEditing] = useState(false);
  const [editSeed, setEditSeed] = useState<unknown>(undefined);
  const [editToken, setEditToken] = useState(0);
  const [renaming, setRenaming] = useState(false);
  const [renameName, setRenameName] = useState("");
  const [archiving, setArchiving] = useState(false);
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
  const archived = Boolean(row.archived_at);
  const busy = pause.isPending || resume.isPending || run.isPending;
  const monitorEvents = (events.data?.items ?? []).filter((event) => event.monitor_id === row.id);
  const eventByJob = new Map(monitorEvents.map((event) => [event.job_id, event.type]));
  const values = row.baseline?.extracted_data ?? {};
  const jobItems = jobs.data?.items ?? [];

  const stats = [
    { label: t("monitors.stat.lastCheck"), value: formatTime(row.last_success_at) },
    {
      label: t("monitors.stat.nextCheck"),
      value: archived
        ? t("monitors.archived.badge")
        : row.status === "active"
          ? formatTime(row.next_run_at)
          : t("monitors.paused"),
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
              {archived ? (
                <Button size="sm" onClick={() => restore.mutate(row.id)} disabled={restore.isPending}>
                  <RotateCcw className="size-3.5" strokeWidth={1.5} />
                  {t("monitors.action.restore")}
                </Button>
              ) : (
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
              )}
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground"
                onClick={() => { setRenameName(row.name); setRenaming(true); }}
              >
                <Pencil className="size-3.5" strokeWidth={1.5} />
                {t("monitors.action.rename")}
              </Button>
              {!archived && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground"
                  onClick={() => setArchiving(true)}
                >
                  <Archive className="size-3.5" strokeWidth={1.5} />
                  {t("monitors.action.archive")}
                </Button>
              )}
            </>
          }
        >
          <div className="flex flex-wrap items-center gap-2 pt-1.5">
            {archived && <Badge tone="neutral">{t("monitors.archived.badge")}</Badge>}
            {!archived && (
              <Badge tone={row.status === "active" ? "success" : "neutral"}>{statusLabel(row.status)}</Badge>
            )}
            {row.health_status === "failed" && <Badge tone="error">{t("monitors.badge.lastCheckFailed")}</Badge>}
            {row.baseline_status !== "ready" && <Badge tone="warning">{t("monitors.badge.baselinePending")}</Badge>}
          </div>
        </PageHeader>
        {(pause.error || resume.error || run.error || derive.error || rename.error
          || archive.error || restore.error) && (
          <p role="alert" className="mb-4 text-sm text-error">
            {errorText(pause.error || resume.error || run.error || derive.error || rename.error
              || archive.error || restore.error)}
          </p>
        )}
        {archived && (
          <p className="mb-4 rounded-lg border bg-muted/30 px-4 py-2.5 text-[13px] text-muted-foreground">
            {t("monitors.archived.note")}
          </p>
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

        <MonitorConfig
          monitor={row}
          onEdit={() => {
            setEditSeed(undefined);
            setEditToken((token) => token + 1);
            setEditing(true);
          }}
          onRestore={(oldSpec) => {
            setEditSeed(oldSpec);
            setEditToken((token) => token + 1);
            setEditing(true);
          }}
        />

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
                        <div className="mt-1.5 flex flex-wrap gap-x-4">
                          {monitorEvents[0].snapshot_id && (
                            <Link
                              href={`/app/monitors/${row.id}/snapshots/${monitorEvents[0].snapshot_id}`}
                              className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                            >
                              {t("monitors.snapshot.open")}
                            </Link>
                          )}
                          <Link
                            href={`/app/monitors/${row.id}?job=${monitorEvents[0].job_id}`}
                            className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                          >
                            {t("monitors.dialog.open")}
                          </Link>
                        </div>
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
                        <div className="flex flex-wrap gap-x-4">
                          {event.snapshot_id && (
                            <Link
                              href={`/app/monitors/${row.id}/snapshots/${event.snapshot_id}`}
                              className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                            >
                              {t("monitors.snapshot.open")}
                            </Link>
                          )}
                          <Link
                            href={`/app/monitors/${row.id}?job=${event.job_id}`}
                            className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                          >
                            {t("monitors.dialog.open")}
                          </Link>
                        </div>
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

            <section>
              <h2 className="section-title mb-2">{t("monitors.snapshots.title")}</h2>
              {snapshots.isPending && <p className="meta">{t("monitors.loadingShort")}</p>}
              {snapshots.error && <p role="alert" className="text-xs text-error">{t("common.listError")}</p>}
              {!snapshots.isPending && !snapshots.error
                && (snapshots.data?.items.length ?? 0) === 0 && (
                  <EmptyState
                    title={t("monitors.snapshots.emptyTitle")}
                    description={t("monitors.snapshots.emptyBody")}
                  />
                )}
              <ul className="border-t">
                {(snapshots.data?.items ?? []).map((snapshot) => (
                  <li key={snapshot.id}>
                    <Link
                      href={`/app/monitors/${row.id}/snapshots/${snapshot.id}`}
                      className="flex items-center gap-3 border-b py-2.5 transition-colors duration-150 hover:bg-muted/60"
                    >
                      <span className="num w-[4.5rem] shrink-0 text-[12px] text-muted-foreground">
                        {formatTime(snapshot.collected_at)}
                      </span>
                      <span className="num shrink-0 text-[11px] text-muted-foreground">
                        {t("monitors.config.versionValue", { version: snapshot.spec_version })}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                        {t("monitors.snapshots.coverage", {
                          coverage: coverageLabel((snapshot.coverage as { scope?: string }).scope),
                        })}
                      </span>
                      <span className="num shrink-0 text-[11px] text-muted-foreground">
                        {t("monitors.snapshots.evidence", { count: snapshot.evidence_refs.length })}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              <ListPagination query={snapshots} />
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
            {row.baseline && (
              <div className="mt-3 border-t pt-3">
                <EvidenceLinks
                  snapshotId={row.baseline.id}
                  references={row.baseline.evidence_refs}
                />
              </div>
            )}
          </aside>
        </div>
      </PageBody>

      <Dialog
        open={Boolean(openJob)}
        onOpenChange={(value) => {
          if (value) return;
          setOpenJob(null);
          if (initialJob) router.replace(`/app/monitors/${row.id}`);
        }}
      >
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
                  <p className="meta mt-2">
                    {t("monitors.dialog.coverage", {
                      coverage: coverageLabel(
                        (detail.data.snapshot.coverage as { scope?: string }).scope,
                      ),
                    })}
                    {(detail.data.snapshot.coverage as { description?: string }).description
                      ? ` · ${(detail.data.snapshot.coverage as { description?: string }).description}`
                      : ""}
                  </p>
                  <div className="mt-2">
                    <EvidenceLinks
                      snapshotId={detail.data.snapshot.id}
                      references={detail.data.snapshot.evidence_refs}
                      full
                    />
                  </div>
                </div>
              )}

              {cancelJob.error && (
                <p role="alert" className="text-xs text-error">{errorText(cancelJob.error)}</p>
              )}
              {detail.data.status === "queued" || detail.data.status === "running" ? (
                <div className="flex justify-end border-t pt-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => cancelJob.mutate(detail.data!.id)}
                    disabled={cancelJob.isPending}
                  >
                    {t("monitors.job.cancel")}
                  </Button>
                </div>
              ) : detail.data.status === "failed" && !archived ? (
                <div className="flex justify-end border-t pt-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => run.mutate(row.id)}
                    disabled={run.isPending || row.status !== "active"}
                  >
                    <RefreshCw strokeWidth={1.5} />
                    {t("monitors.job.retry")}
                  </Button>
                </div>
              ) : null}

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

      <MonitorEditor
        monitorId={row.id}
        spec={row.spec}
        seedSpec={editSeed}
        seedToken={editToken}
        open={editing}
        onOpenChange={setEditing}
      />

      <Dialog open={renaming} onOpenChange={setRenaming}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">{t("monitors.rename.title")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="monitor-name">{t("monitors.rename.label")}</Label>
              <Input
                id="monitor-name"
                value={renameName}
                maxLength={200}
                onChange={(event) => setRenameName(event.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setRenaming(false)}>
                {t("monitors.editor.cancel")}
              </Button>
              <Button
                size="sm"
                disabled={!renameName.trim() || rename.isPending}
                onClick={() => rename.mutate(
                  { monitorId: row.id, name: renameName.trim() },
                  { onSuccess: () => setRenaming(false) },
                )}
              >
                {t("monitors.rename.save")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={archiving} onOpenChange={setArchiving}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">{t("monitors.archive.title")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="meta leading-5">{t("monitors.archive.body", { name: row.name })}</p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setArchiving(false)}>
                {t("monitors.editor.cancel")}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={archive.isPending}
                onClick={() => archive.mutate(row.id, { onSuccess: () => setArchiving(false) })}
              >
                <Archive strokeWidth={1.5} />
                {t("monitors.action.archive")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
