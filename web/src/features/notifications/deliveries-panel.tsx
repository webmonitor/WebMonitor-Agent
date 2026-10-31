"use client";
import { useState } from "react";
import { Mail } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/empty-state";
import { useDeliveries } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { ListPagination } from "@/components/list-pagination";

const TONES = { sent: "success", failed: "error", retrying: "warning", sending: "warning" } as const;

function tone(status: string) {
  return TONES[status as keyof typeof TONES] ?? "neutral";
}

export function DeliveriesPanel() {
  const { t } = useI18n();
  const { statusLabel, errorText, formatDateTime, formatTime } = useFormat();
  const deliveries = useDeliveries();
  const [openId, setOpenId] = useState<string | null>(null);
  const items = deliveries.data?.items ?? [];
  const open = items.find((delivery) => delivery.id === openId) ?? null;

  return (
    <section className="space-y-3">
      <header>
        <h2 className="text-sm font-semibold">{t("activity.deliveries.title")}</h2>
        <p className="meta mt-0.5">{t("activity.deliveries.description")}</p>
      </header>

      {deliveries.isPending && <p className="meta">{t("activity.deliveries.loading")}</p>}

      {!deliveries.isPending && !deliveries.error && items.length === 0 && (
        <EmptyState
          title={t("activity.deliveries.emptyTitle")}
          description={t("activity.deliveries.emptyDescription")}
        />
      )}

      <ul className="space-y-2">
        {items.map((delivery) => (
          <li key={delivery.id}>
            <button
              className="surface flex w-full items-start gap-3 p-3 text-left transition-colors hover:border-ring/40"
              onClick={() => setOpenId(delivery.id)}
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
      <ListPagination query={deliveries} />

      <Dialog open={Boolean(open)} onOpenChange={(value) => !value && setOpenId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="pr-6 text-base">{open?.subject}</DialogTitle>
          </DialogHeader>
          {open && (
            <div className="space-y-3">
              <dl className="grid grid-cols-2 gap-3 text-[13px]">
                <div>
                  <dt className="meta">{t("activity.deliveries.recipient")}</dt>
                  <dd className="truncate">{open.recipient}</dd>
                </div>
                <div>
                  <dt className="meta">{t("activity.deliveries.status")}</dt>
                  <dd>
                    {statusLabel(open.status)}
                    {open.attempt_count > 1
                      ? ` · ${t("activity.deliveries.attempts", { count: open.attempt_count })}`
                      : ""}
                  </dd>
                </div>
                <div>
                  <dt className="meta">{t("activity.deliveries.createdAt")}</dt>
                  <dd>{formatDateTime(open.created_at)}</dd>
                </div>
                <div>
                  <dt className="meta">{t("activity.deliveries.sentAt")}</dt>
                  <dd>{formatDateTime(open.sent_at)}</dd>
                </div>
              </dl>
              {open.error_code && (
                <p className="rounded-lg border border-error/25 bg-error/5 px-3 py-2 text-xs text-error">
                  {open.error_message
                    ? t("activity.deliveries.errorDetail", {
                        code: errorText(open.error_code),
                        message: open.error_message,
                      })
                    : errorText(open.error_code)}
                </p>
              )}
              <div>
                <h3 className="meta mb-1">{t("activity.deliveries.body")}</h3>
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
