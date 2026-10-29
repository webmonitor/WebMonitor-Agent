"use client";
import { useState } from "react";
import { Mail } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/empty-state";
import { useDeliveries, type Delivery } from "@/lib/api/hooks";
import { errorText, formatDateTime, formatTime, statusLabel } from "@/lib/format";

const TONES = { sent: "success", failed: "error", retrying: "warning", sending: "warning" } as const;

function tone(status: string) {
  return TONES[status as keyof typeof TONES] ?? "neutral";
}

export function DeliveriesPanel() {
  const deliveries = useDeliveries();
  const [open, setOpen] = useState<Delivery | null>(null);
  const items = deliveries.data?.items ?? [];

  return (
    <section className="space-y-3">
      <header>
        <h2 className="text-sm font-semibold">投递记录</h2>
        <p className="meta mt-0.5">“已发送”表示邮件服务器已接收，不代表一定进入收件箱。</p>
      </header>

      {deliveries.isPending && <p className="meta">正在加载…</p>}

      {!deliveries.isPending && items.length === 0 && (
        <EmptyState title="还没有投递记录" description="监控发现变化后，发往通知组的邮件会记录在这里。" />
      )}

      <ul className="space-y-2">
        {items.map((delivery) => (
          <li key={delivery.id}>
            <button
              className="surface flex w-full items-start gap-3 p-3 text-left transition-colors hover:border-ring/40"
              onClick={() => setOpen(delivery)}
            >
              <Mail className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1">
                <span className="flex items-start justify-between gap-2">
                  <span className="truncate text-[13px] font-medium">{delivery.subject}</span>
                  <Badge tone={tone(delivery.status)}>{statusLabel(delivery.status)}</Badge>
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                  {delivery.recipient} · {formatTime(delivery.created_at)}
                </span>
                {delivery.error_code && (
                  <span className="mt-1 block text-[11px] text-error">{errorText(delivery.error_code)}</span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <Dialog open={Boolean(open)} onOpenChange={(value) => !value && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="pr-6 text-base">{open?.subject}</DialogTitle>
          </DialogHeader>
          {open && (
            <div className="space-y-3">
              <dl className="grid grid-cols-2 gap-3 text-[13px]">
                <div>
                  <dt className="meta">收件人</dt>
                  <dd className="truncate">{open.recipient}</dd>
                </div>
                <div>
                  <dt className="meta">状态</dt>
                  <dd>
                    {statusLabel(open.status)}
                    {open.attempt_count > 1 ? ` · 尝试 ${open.attempt_count} 次` : ""}
                  </dd>
                </div>
                <div>
                  <dt className="meta">创建时间</dt>
                  <dd>{formatDateTime(open.created_at)}</dd>
                </div>
                <div>
                  <dt className="meta">发送时间</dt>
                  <dd>{formatDateTime(open.sent_at)}</dd>
                </div>
              </dl>
              {open.error_code && (
                <p className="rounded-lg border border-error/25 bg-error/5 px-3 py-2 text-xs text-error">
                  {errorText(open.error_code)}
                  {open.error_message ? `：${open.error_message}` : ""}
                </p>
              )}
              <div>
                <h3 className="meta mb-1">正文</h3>
                <pre className="max-h-72 overflow-auto rounded-lg border bg-muted/40 p-3 text-[12px] leading-relaxed text-foreground">
                  {open.body_text}
                </pre>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
