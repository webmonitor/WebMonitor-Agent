"use client";
import { useDeliveries } from "@/lib/api/hooks";
import { formatTime, statusLabel } from "@/lib/format";

export function DeliveriesPanel() {
  const deliveries = useDeliveries();
  const items = deliveries.data?.items ?? [];
  return (
    <section className="space-y-2">
      <header>
        <h2>邮件投递</h2>
        <p className="text-xs text-muted-foreground">“已发送”表示 SMTP 已接收，不代表进入收件箱。</p>
      </header>
      {deliveries.isPending && <p className="text-sm text-muted-foreground">正在加载…</p>}
      {deliveries.error && <p className="text-sm text-error">{deliveries.error.message}</p>}
      <ul className="space-y-2">
        {items.map((delivery) => (
          <li key={delivery.id} className="rounded-xl border bg-card px-4 py-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-medium">{delivery.subject}</p>
                <p className="break-words text-xs text-muted-foreground">
                  {delivery.recipient} · {formatTime(delivery.created_at)} · 尝试 {delivery.attempt_count} 次
                </p>
              </div>
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{statusLabel(delivery.status)}</span>
            </div>
            {delivery.error_code && (
              <p className="mt-1 text-xs text-error">
                {delivery.error_code}: {delivery.error_message}
              </p>
            )}
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-muted-foreground">正文</summary>
              <pre className="mt-1 max-h-48 overflow-auto">{delivery.body_text}</pre>
            </details>
          </li>
        ))}
      </ul>
      {items.length === 0 && !deliveries.isPending && (
        <p className="text-sm text-muted-foreground">还没有投递记录。</p>
      )}
    </section>
  );
}
