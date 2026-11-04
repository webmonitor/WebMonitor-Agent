"use client";
import { useState } from "react";
import { Mail, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/empty-state";
import { Select } from "@/components/ui/select";
import { useDeliveries, useRetryDelivery } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { ListPagination } from "@/components/list-pagination";

const TONES = { sent: "success", failed: "error", retrying: "warning", sending: "warning" } as const;

function tone(status: string) {
  return TONES[status as keyof typeof TONES] ?? "neutral";
}

const STATUSES = ["queued", "sending", "retrying", "sent", "failed", "cancelled"];

export function DeliveriesPanel() {
  const { t } = useI18n();
  const { statusLabel, errorText, formatDateTime, formatTime } = useFormat();
  const [status, setStatus] = useState("");
  const deliveries = useDeliveries(status || undefined);
  const retry = useRetryDelivery();
  const [openId, setOpenId] = useState<string | null>(null);
  const items = deliveries.data?.items ?? [];
  const open = items.find((delivery) => delivery.id === openId) ?? null;
  const retryable = open ? ["failed", "cancelled"].includes(open.status) : false;

  return (
    <section>
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="section-title">{t("activity.deliveries.title")}</h2>
          <p className="meta mt-1 leading-5">{t("activity.deliveries.description")}</p>
        </div>
        <Select
          label={t("activity.deliveries.status")}
          value={status}
          placeholder={t("activity.deliveries.allStatuses")}
          onChange={setStatus}
          className="w-32 shrink-0"
          menuClassName="left-auto right-0"
          options={[
            { value: "", label: t("activity.deliveries.allStatuses") },
            ...STATUSES.map((value) => ({ value, label: statusLabel(value) })),
          ]}
        />
      </header>
      {retry.error && <p role="alert" className="text-xs text-error">{errorText(retry.error)}</p>}

      {deliveries.isPending && <p className="meta">{t("activity.deliveries.loading")}</p>}

      {!deliveries.isPending && !deliveries.error && items.length === 0 && (
        <EmptyState
          title={t("activity.deliveries.emptyTitle")}
          description={t("activity.deliveries.emptyDescription")}
        />
      )}

      <ul className="divide-y border-t">
        {items.map((delivery) => (
          <li key={delivery.id}>
            <button
              className="flex w-full items-start gap-3 py-3 text-left transition-colors duration-150 hover:bg-muted/50"
              onClick={() => setOpenId(delivery.id)}
            >
              <Mail className="mt-0.5 size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
              <span className="min-w-0 flex-1">
                <span className="flex items-start justify-between gap-2">
                  <span className="truncate text-[13px] font-medium">{delivery.subject}</span>
                  <Badge tone={tone(delivery.status)}>{statusLabel(delivery.status)}</Badge>
                </span>
                <span className="num mt-1 block truncate text-[11px] text-muted-foreground">
                  {delivery.monitor_name} · {delivery.recipient} · {formatTime(delivery.created_at)}
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
            <div className="space-y-4">
              <dl className="grid grid-cols-2 gap-3 text-[13px]">
                <div>
                  <dt className="label-line">{t("activity.deliveries.recipient")}</dt>
                  <dd className="num truncate">{open.recipient}</dd>
                </div>
                <div>
                  <dt className="label-line">{t("activity.deliveries.status")}</dt>
                  <dd>
                    {statusLabel(open.status)}
                    {open.attempt_count > 1
                      ? ` · ${t("activity.deliveries.attempts", { count: open.attempt_count })}`
                      : ""}
                  </dd>
                </div>
                <div>
                  <dt className="label-line">{t("activity.deliveries.createdAt")}</dt>
                  <dd className="num">{formatDateTime(open.created_at)}</dd>
                </div>
                <div>
                  <dt className="label-line">{t("activity.deliveries.sentAt")}</dt>
                  <dd className="num">{formatDateTime(open.sent_at)}</dd>
                </div>
              </dl>
              {open.error_code && (
                <p className="border-l-2 border-error/40 pl-2.5 text-xs leading-5 text-error">
                  {open.error_message
                    ? t("activity.deliveries.errorDetail", {
                        code: errorText(open.error_code),
                        message: open.error_message,
                      })
                    : errorText(open.error_code)}
                </p>
              )}
              {retryable && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 px-2 text-xs"
                  disabled={retry.isPending}
                  onClick={() => retry.mutate(open.id)}
                >
                  <RefreshCw strokeWidth={1.5} />
                  {t("common.retry")}
                </Button>
              )}
              <div>
                <h3 className="label-line mb-1.5">{t("activity.deliveries.body")}</h3>
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
