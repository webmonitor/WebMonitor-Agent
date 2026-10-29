"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Pause, Play, RefreshCw, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  useDeriveDraft,
  useJobDetail,
  useMonitor,
  useMonitorJobs,
  usePauseMonitor,
  useResumeMonitor,
  useRunNow,
} from "@/lib/api/hooks";
import { baselineLabel, formatJson, formatTime, statusLabel } from "@/lib/format";

export function MonitorPage({ monitorId }: { monitorId: string }) {
  const monitor = useMonitor(monitorId);
  const jobs = useMonitorJobs(monitorId);
  const pause = usePauseMonitor();
  const resume = useResumeMonitor();
  const run = useRunNow();
  const derive = useDeriveDraft();
  const router = useRouter();
  const [openJob, setOpenJob] = useState<string | null>(null);
  const detail = useJobDetail(openJob);

  if (monitor.isPending) return <p className="p-6 text-sm text-muted-foreground">正在加载监控…</p>;
  if (monitor.error) return <p className="p-6 text-sm text-error">{monitor.error.message}</p>;
  if (!monitor.data) return null;

  const row = monitor.data;
  const busy = pause.isPending || resume.isPending || run.isPending;

  return (
    <div className="h-full overflow-y-auto px-4 py-5">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate">{row.name}</h1>
          <a className="break-all text-xs underline" href={row.url} target="_blank" rel="noreferrer">
            {row.url}
          </a>
          <p className="mt-1 text-xs text-muted-foreground">
            {statusLabel(row.status)} · {statusLabel(row.collection_mode)} · 每 {row.interval_seconds} 秒 ·{" "}
            {row.timezone} · v{row.spec_version}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {row.status === "active" ? (
            <Button variant="outline" size="sm" onClick={() => void pause.mutateAsync(row.id)} disabled={busy}>
              <Pause />
              暂停
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={() => void resume.mutateAsync(row.id)} disabled={busy}>
              <Play />
              恢复
            </Button>
          )}
          <Button size="sm" onClick={() => void run.mutateAsync(row.id)} disabled={busy}>
            <Zap />
            立即运行
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={derive.isPending}
            onClick={async () => {
              const result = await derive.mutateAsync(row.id);
              router.push(`/app?conversation=${result.conversation_id}`);
            }}
          >
            <RefreshCw />
            修改通知
          </Button>
        </div>
      </header>

      <dl className="mb-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-muted-foreground">基线</dt><dd>{baselineLabel(row.baseline_status)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">健康</dt><dd>{statusLabel(row.health_status)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">下次运行</dt><dd>{formatTime(row.next_run_at)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">上次成功</dt><dd>{formatTime(row.last_success_at)}</dd></div>
      </dl>

      {row.baseline && (
        <details className="mb-5 rounded-xl border bg-card px-4 py-3 text-sm">
          <summary className="cursor-pointer text-xs text-muted-foreground">
            基线快照 · {formatTime(row.baseline.collected_at)}
          </summary>
          <pre className="mt-2 max-h-64 overflow-auto">{formatJson(row.baseline.extracted_data)}</pre>
          <p className="mt-2 flex flex-wrap gap-3 text-xs">
            {row.baseline.evidence_refs.map((reference, index) => (
              <a
                key={reference.sha256}
                className="underline"
                href={`/api/v1/snapshots/${row.baseline?.id}/evidence/${index}`}
                target="_blank"
                rel="noreferrer"
              >
                {reference.kind === "screenshot" ? "截图" : "HTML"}
              </a>
            ))}
          </p>
        </details>
      )}

      <section>
        <h2 className="mb-2 text-sm font-medium">采集历史</h2>
        {jobs.isPending && <p className="text-sm text-muted-foreground">正在加载…</p>}
        <ul className="space-y-1">
          {(jobs.data?.items ?? []).map((job) => (
            <li key={job.id}>
              <button
                className="flex w-full items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2 text-left text-xs hover:bg-muted"
                onClick={() => setOpenJob(job.id)}
              >
                <span>
                  {formatTime(job.created_at)} · {statusLabel(job.status)}
                  {job.error_code ? ` · ${job.error_code}` : ""}
                </span>
                <span className="text-muted-foreground">尝试 {job.attempt_count} 次</span>
              </button>
            </li>
          ))}
        </ul>
        {jobs.data?.items.length === 0 && (
          <p className="text-sm text-muted-foreground">还没有采集记录。等待下一个调度周期或点“立即运行”。</p>
        )}
      </section>

      <Dialog open={Boolean(openJob)} onOpenChange={(value) => !value && setOpenJob(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>运行详情</DialogTitle>
          </DialogHeader>
          {detail.isPending && <p className="text-sm text-muted-foreground">正在加载…</p>}
          {detail.data && (
            <div className="space-y-3 text-sm">
              <p className="text-xs text-muted-foreground">
                {statusLabel(detail.data.status)} · 尝试 {detail.data.attempt_count} 次 ·{" "}
                {formatTime(detail.data.created_at)}
              </p>
              {detail.data.error_code && (
                <p className="text-error">{detail.data.error_code}: {detail.data.error_message}</p>
              )}
              <div>
                <h3 className="text-xs font-medium text-muted-foreground">尝试记录</h3>
                <pre className="max-h-40 overflow-auto">{formatJson(detail.data.attempts)}</pre>
              </div>
              {detail.data.snapshot && (
                <>
                  <div>
                    <h3 className="text-xs font-medium text-muted-foreground">提取结果</h3>
                    <pre className="max-h-64 overflow-auto">
                      {formatJson(detail.data.snapshot.extracted_data)}
                    </pre>
                  </div>
                  <p className="flex flex-wrap gap-3 text-xs">
                    {detail.data.snapshot.evidence_refs.map((reference, index) => (
                      <a
                        key={reference.sha256}
                        className="underline"
                        href={`/api/v1/snapshots/${detail.data?.snapshot?.id}/evidence/${index}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {reference.kind === "screenshot" ? "截图" : "HTML"}
                      </a>
                    ))}
                  </p>
                </>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
