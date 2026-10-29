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
import {
  errorText,
  eventLabel,
  formatBytes,
  formatClock,
  formatDateTime,
  formatInterval,
  formatMode,
  formatTime,
  formatValue,
  statusLabel,
  fieldLabels,
} from "@/lib/format";
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
  const entries = Object.entries(values);
  if (entries.length === 0) return <p className="meta">没有采集到内容。</p>;
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
        <p className="meta">正在读取监控…</p>
      </div>
    );
  }
  if (monitor.error || !monitor.data) {
    return (
      <div className="grid h-full place-items-center px-6 text-center">
        <div className="space-y-2">
          <p className="text-sm font-medium">找不到这个监控</p>
          <p className="meta">请确认链接是否完整，或联系管理员检查你的查看权限。</p>
          <Link className="text-sm text-primary underline-offset-2 hover:underline" href="/app">
            返回对话
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
    { label: "上次检查", value: formatTime(row.last_success_at) },
    { label: "下次检查", value: row.status === "active" ? formatTime(row.next_run_at) : "暂停中" },
    { label: "检查频率", value: formatInterval(row.interval_seconds) },
    { label: "采集方式", value: formatMode(row.collection_mode) },
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
                  暂停
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => void resume.mutateAsync(row.id)} disabled={busy}>
                  <Play className="size-3.5" />
                  恢复
                </Button>
              )}
              <Button size="sm" onClick={() => void run.mutateAsync(row.id)} disabled={busy}>
                <Zap className="size-3.5" />
                立即检查
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
                修改设置
              </Button>
            </>
          }
        >
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Badge tone={row.status === "active" ? "success" : "neutral"}>{statusLabel(row.status)}</Badge>
            {row.health_status === "failed" && <Badge tone="error">最近一次采集失败</Badge>}
            {row.baseline_status !== "ready" && <Badge tone="warning">正在建立基线</Badge>}
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
            <h2 className="section-title">最近检查</h2>
            {jobs.isPending && <p className="meta">正在加载…</p>}
            {!jobs.isPending && (jobs.data?.items.length ?? 0) === 0 && (
              <EmptyState
                title="还没有检查记录"
                description="等到下一个检查周期，或者点右上角「立即检查」。"
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
                          ? `发现${eventLabel(eventByJob.get(job.id))}`
                          : job.status === "succeeded"
                            ? "内容已保存"
                            : ""}
                    </span>
                    {job.attempt_count > 1 && (
                      <span className="meta shrink-0 tabular-nums">尝试 {job.attempt_count} 次</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <aside className="space-y-4">
            <section className="surface-pad space-y-3">
              <div className="flex items-baseline justify-between">
                <h2 className="section-title">当前内容</h2>
                <span className="meta">{row.baseline ? formatTime(row.baseline.collected_at) : "—"}</span>
              </div>
              {row.baseline ? (
                <FieldValues values={values} labels={labels} />
              ) : (
                <p className="meta">第一次采集成功后，这里会显示页面上的当前内容。</p>
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
                      {reference.kind === "screenshot" ? "截图" : "页面存档"}
                      <span className="tabular-nums">{formatBytes(reference.size_bytes)}</span>
                    </a>
                  ))}
                </div>
              )}
            </section>

            <section className="space-y-2">
              <div className="flex items-baseline justify-between">
                <h2 className="section-title">最近事件</h2>
                <Link href="/app/events" className="text-xs text-primary underline-offset-2 hover:underline">
                  全部
                </Link>
              </div>
              {monitorEvents.length === 0 ? (
                <p className="meta">这个监控还没有产生过事件。</p>
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
            <DialogTitle className="text-base">检查详情</DialogTitle>
          </DialogHeader>
          {detail.isPending && <p className="meta">正在加载…</p>}
          {detail.data && (
            <div className="space-y-4 text-[13px]">
              <dl className="grid grid-cols-2 gap-3">
                <div>
                  <dt className="meta">状态</dt>
                  <dd>{statusLabel(detail.data.status)}</dd>
                </div>
                <div>
                  <dt className="meta">开始时间</dt>
                  <dd>{formatDateTime(detail.data.created_at)}</dd>
                </div>
                <div>
                  <dt className="meta">尝试次数</dt>
                  <dd className="tabular-nums">{detail.data.attempt_count}</dd>
                </div>
                <div>
                  <dt className="meta">结束时间</dt>
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
                  <h3 className="meta">采集到的内容</h3>
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
                          {reference.kind === "screenshot" ? "页面截图" : "页面存档"}
                          <span className="tabular-nums">{formatBytes(reference.size_bytes)}</span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {detail.data.attempts.length > 1 && (
                <div className="space-y-1.5">
                  <h3 className="meta">尝试记录</h3>
                  <ul className="divide-y rounded-lg border">
                    {detail.data.attempts.map((attempt) => (
                      <li key={attempt.number} className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs">
                        <span>
                          第 {attempt.number} 次 · {statusLabel(attempt.status)}
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
