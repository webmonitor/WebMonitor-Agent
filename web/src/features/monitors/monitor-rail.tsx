"use client";
import Link from "next/link";
import { useMonitors } from "@/lib/api/hooks";
import { baselineLabel, formatTime, statusLabel } from "@/lib/format";

export function MonitorRail({ activeId }: { activeId?: string }) {
  const monitors = useMonitors();
  const items = monitors.data?.items ?? [];
  return (
    <section className="space-y-2">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-medium">监控</h2>
        <span className="text-xs text-muted-foreground">{monitors.data?.total ?? 0}</span>
      </header>
      {monitors.isPending && <p className="text-xs text-muted-foreground">正在加载…</p>}
      {monitors.error && <p className="text-xs text-error">{monitors.error.message}</p>}
      {items.length === 0 && !monitors.isPending && (
        <p className="text-xs text-muted-foreground">还没有监控。先在对话中完成预览并确认创建。</p>
      )}
      <ul className="space-y-1">
        {items.map((monitor) => (
          <li key={monitor.id}>
            <Link
              href={`/app/monitors/${monitor.id}`}
              className={`block rounded-lg border px-3 py-2 text-xs hover:bg-muted ${
                monitor.id === activeId ? "bg-accent" : "bg-card"
              }`}
            >
              <span className="block truncate text-sm">{monitor.name}</span>
              <span className="text-muted-foreground">
                {statusLabel(monitor.status)} · {baselineLabel(monitor.baseline_status)}
              </span>
              <span className="block text-muted-foreground">
                下次 {formatTime(monitor.next_run_at)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
