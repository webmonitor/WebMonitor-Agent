"use client";
import Link from "next/link";
import { Check, CheckCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { EventView } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Tone = "brand" | "success" | "warning" | "error" | "neutral";

const TONES: Record<string, Tone> = {
  list_changed: "brand",
  content_changed: "brand",
  run_failed: "error",
  recovered: "success",
};

type Difference = {
  field?: string;
  type?: string;
  before?: unknown;
  after?: unknown;
  items?: unknown[];
  delta?: string;
  percent_change?: string;
  keyword?: string;
  operator?: string;
  value?: string;
};

function differencesOf(change: Record<string, unknown>): Difference[] {
  const raw = change.differences;
  if (Array.isArray(raw) && raw.length > 0) return raw as Difference[];
  const before = change.before;
  const after = change.after;
  if (!before || !after || typeof before !== "object" || typeof after !== "object") return [];
  const rows: Difference[] = [];
  for (const [field, value] of Object.entries(after as Record<string, unknown>)) {
    const previous = (before as Record<string, unknown>)[field];
    if (JSON.stringify(previous) !== JSON.stringify(value)) {
      rows.push({ field, before: previous, after: value });
    }
  }
  return rows;
}

function ItemFields({ item, labels }: { item: unknown; labels: Record<string, string> }) {
  const { formatValue } = useFormat();
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return <span className="num break-words">{formatValue(item)}</span>;
  }
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-0.5">
      {Object.entries(item as Record<string, unknown>).map(([key, value]) => (
        <span key={key} className="inline-flex items-baseline gap-1">
          <span className="text-[13px] text-muted-foreground">{labels[key] ?? key}</span>
          <span className="num break-words">{formatValue(value)}</span>
        </span>
      ))}
    </span>
  );
}

function UpdatedFields({ item, labels }: { item: unknown; labels: Record<string, string> }) {
  const { formatValue } = useFormat();
  if (!item || typeof item !== "object") return null;
  const record = item as {
    before?: Record<string, unknown>;
    after?: Record<string, unknown>;
    fields?: string[];
  };
  return (
    <ul className="space-y-0.5">
      {(record.fields ?? []).map((name) => (
        <li key={name} className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-[13px] text-muted-foreground">{labels[name] ?? name}</span>
          <span className="num text-[13px] text-muted-soft line-through decoration-muted-soft/50">
            {formatValue(record.before?.[name])}
          </span>
          <span aria-hidden className="text-[12px] text-muted-soft">→</span>
          <span className="num text-[13px] text-ink">{formatValue(record.after?.[name])}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The change itself, written as ink on ruled paper: the old value struck, the
 * new value in the accent. List rules show the rows that appeared, disappeared
 * or changed instead of flattening the whole list into one string.
 */
export function ChangeRows({
  change,
  type,
}: {
  change: Record<string, unknown>;
  type?: string;
}) {
  const { t } = useI18n();
  const { fieldLabel, formatValue } = useFormat();
  if (type === "run_failed") {
    return <p className="text-[14px] leading-6 text-muted-foreground">{t("activity.eventCard.failedNote")}</p>;
  }
  if (type === "recovered") {
    return <p className="text-[14px] leading-6 text-muted-foreground">{t("activity.eventCard.recoveredNote")}</p>;
  }
  const labels = (change.labels ?? {}) as Record<string, string>;
  const rows = differencesOf(change);
  if (rows.length === 0) {
    return <p className="text-[14px] leading-6 text-muted-foreground">{t("activity.eventCard.noFields")}</p>;
  }
  return (
    <dl className="divide-y">
      {rows.map((row, index) => {
        const items = Array.isArray(row.items) ? row.items : [];
        const metrics = [
          row.keyword ? t("activity.eventCard.keyword", { keyword: row.keyword }) : "",
          row.delta ? t("activity.eventCard.delta", { value: row.delta }) : "",
          row.percent_change
            ? t("activity.eventCard.percent", { value: Number(row.percent_change).toFixed(1) })
            : "",
        ].filter(Boolean);
        return (
          <div key={`${row.field ?? index}-${index}`} className="space-y-1 py-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="shrink-0 text-[13px] text-muted-foreground">
                {fieldLabel({ name: row.field ?? "", semantic: labels[row.field ?? ""] })}
              </dt>
              {items.length > 0 ? (
                <dd className="num shrink-0 text-[13px] text-muted-foreground">
                  {t("activity.eventCard.itemCount", { count: items.length })}
                </dd>
              ) : metrics.length === 0 ? (
                <dd className="flex min-w-0 flex-wrap items-baseline justify-end gap-x-2 gap-y-0.5 text-right">
                  <span className="num text-[13px] text-muted-soft line-through decoration-muted-soft/50">
                    {formatValue(row.before)}
                  </span>
                  <span aria-hidden className="text-[13px] text-muted-foreground/60">→</span>
                  <span className="num text-[14px] font-medium text-ink">
                    {formatValue(row.after)}
                  </span>
                </dd>
              ) : (
                <dd className="num shrink-0 text-[13px] text-muted-foreground">
                  {metrics.join(" · ")}
                </dd>
              )}
            </div>
            {items.length > 0 && (
              <dd>
                <ul className="space-y-1 border-l border-hairline pl-2.5">
                  {items.map((item, itemIndex) => (
                    <li key={itemIndex} className="text-[13px]">
                      {row.type === "list_updated" ? (
                        <UpdatedFields item={item} labels={labels} />
                      ) : (
                        <span className="flex items-baseline gap-1.5">
                          <span
                            aria-hidden
                            className={`shrink-0 ${
                              row.type === "list_removed" ? "text-error" : "text-success-ink"
                            }`}
                          >
                            {row.type === "list_removed" ? "−" : "+"}
                          </span>
                          <ItemFields item={item} labels={labels} />
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}

export function EventCard({
  event,
  onAcknowledge,
  acknowledging,
}: {
  event: EventView;
  onAcknowledge?: (id: string) => void;
  acknowledging?: boolean;
}) {
  const { t } = useI18n();
  const { eventLabel, errorText, formatTime } = useFormat();
  const unread = !event.acknowledged_at;
  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TONES[event.type] ?? "neutral"}>{eventLabel(event.type)}</Badge>
            <Link
              href={`/app/monitors/${event.monitor_id}`}
              className="truncate text-[15px] font-medium text-ink underline-offset-2 hover:underline"
            >
              {event.monitor_name}
            </Link>
            {/* Unread is a dot in the same column as the live monitors, not a stripe. */}
            {unread && <span aria-hidden className="size-1.5 rounded-full bg-primary" />}
          </div>
          <p className="num text-[12px] text-muted-soft">{formatTime(event.created_at)}</p>
        </div>
        {onAcknowledge &&
          (unread ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 shrink-0 px-2 text-[13px] text-muted-soft hover:text-ink"
              onClick={() => onAcknowledge(event.id)}
              disabled={acknowledging}
            >
              <Check className="size-3.5" strokeWidth={1.5} />
              {t("activity.eventCard.acknowledge")}
            </Button>
          ) : (
            <span className="flex shrink-0 items-center gap-1 text-[13px] text-muted-soft">
              <CheckCheck className="size-3.5" strokeWidth={1.5} />
              {t("activity.eventCard.read")}
            </span>
          ))}
      </div>
      <div className="mt-2">
        <ChangeRows change={event.change} type={event.type} />
      </div>
      {event.notifications_skipped && (
        <p role="status" className="mt-2 text-[13px] leading-5 text-warning-ink">
          {t("activity.eventCard.notificationsSkipped")}{" "}
          {errorText(event.notifications_skipped)}
        </p>
      )}
      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
        {event.snapshot_id && (
          <Link
            href={`/app/monitors/${event.monitor_id}/snapshots/${event.snapshot_id}`}
            className="text-[13px] text-muted-soft hover:text-ink hover:underline"
          >
            {t("monitors.snapshot.open")}
          </Link>
        )}
        <Link
          href={`/app/monitors/${event.monitor_id}?job=${event.job_id}`}
          className="text-[13px] text-muted-soft hover:text-ink hover:underline"
        >
          {t("monitors.dialog.open")}
        </Link>
      </div>
    </li>
  );
}
