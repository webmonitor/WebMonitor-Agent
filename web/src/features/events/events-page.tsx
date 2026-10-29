"use client";
import Link from "next/link";
import { useAckEvent, useEvents } from "@/lib/api/hooks";
import { formatTime, statusLabel } from "@/lib/format";

export function EventsPage() {
  const events = useEvents();
  const acknowledge = useAckEvent();
  const items = events.data?.items ?? [];

  return (
    <div className="h-full overflow-y-auto px-4 py-5">
      <header className="mb-4">
        <h1>变化事件</h1>
        <p className="text-sm text-muted-foreground">
          首次成功采集只建立基线，不会产生事件。事件与通知相互对应。
        </p>
      </header>
      {events.isPending && <p className="text-sm text-muted-foreground">正在加载…</p>}
      {events.error && <p className="text-sm text-error">{events.error.message}</p>}
      {items.length === 0 && !events.isPending && (
        <p className="text-sm text-muted-foreground">还没有事件。</p>
      )}
      <ul className="space-y-2">
        {items.map((event) => (
          <li key={event.id} className="rounded-xl border bg-card px-4 py-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium">
                  {statusLabel(event.type)} ·{" "}
                  <Link className="underline" href={`/app/monitors/${event.monitor_id}`}>
                    {event.monitor_name}
                  </Link>
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatTime(event.created_at)} ·{" "}
                  {event.acknowledged_at ? `已确认 ${formatTime(event.acknowledged_at)}` : "未确认"}
                </p>
              </div>
              {!event.acknowledged_at && (
                <button
                  className="rounded-lg border px-3 py-1 text-xs hover:bg-muted"
                  onClick={() => void acknowledge.mutateAsync(event.id)}
                  disabled={acknowledge.isPending}
                >
                  确认
                </button>
              )}
            </div>
            <p className="mt-2 break-words text-xs">{String(event.change.summary ?? "")}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
