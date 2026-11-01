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
  price_changed: "brand",
  list_changed: "brand",
  content_changed: "brand",
  run_failed: "error",
  recovered: "success",
};

type Difference = { field?: string; before?: unknown; after?: unknown };

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

/**
 * The change itself, written as ink on ruled paper: the old value struck, the
 * new value in the accent. This is the thing the product exists to produce.
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
    return <p className="text-[13px] leading-6 text-muted-foreground">{t("activity.eventCard.failedNote")}</p>;
  }
  if (type === "recovered") {
    return <p className="text-[13px] leading-6 text-muted-foreground">{t("activity.eventCard.recoveredNote")}</p>;
  }
  const labels = (change.labels ?? {}) as Record<string, string>;
  const rows = differencesOf(change);
  if (rows.length === 0) {
    return <p className="text-[13px] leading-6 text-muted-foreground">{t("activity.eventCard.noFields")}</p>;
  }
  return (
    <dl className="divide-y">
      {rows.map((row, index) => (
        <div
          key={`${row.field ?? index}-${index}`}
          className="flex items-baseline justify-between gap-3 py-1.5"
        >
          <dt className="shrink-0 text-[12px] text-muted-foreground">
            {fieldLabel({ name: row.field ?? "", semantic: labels[row.field ?? ""] })}
          </dt>
          <dd className="flex min-w-0 flex-wrap items-baseline justify-end gap-x-2 gap-y-0.5 text-right">
            <span className="num text-[12px] text-muted-foreground line-through decoration-muted-foreground/40">
              {formatValue(row.before)}
            </span>
            <span aria-hidden className="text-[11px] text-muted-foreground/60">→</span>
            <span className="num text-[13px] font-medium text-foreground">{formatValue(row.after)}</span>
          </dd>
        </div>
      ))}
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
  const { eventLabel, formatTime } = useFormat();
  const unread = !event.acknowledged_at;
  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TONES[event.type] ?? "neutral"}>{eventLabel(event.type)}</Badge>
            <Link
              href={`/app/monitors/${event.monitor_id}`}
              className="truncate text-[13px] font-medium underline-offset-2 hover:underline"
            >
              {event.monitor_name}
            </Link>
            {/* Unread is a dot in the same column as the live monitors, not a stripe. */}
            {unread && <span aria-hidden className="size-1.5 rounded-full bg-foreground" />}
          </div>
          <p className="num text-[11px] text-muted-foreground">{formatTime(event.created_at)}</p>
        </div>
        {onAcknowledge &&
          (unread ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 shrink-0 px-2 text-xs text-muted-foreground"
              onClick={() => onAcknowledge(event.id)}
              disabled={acknowledging}
            >
              <Check className="size-3.5" strokeWidth={1.5} />
              {t("activity.eventCard.acknowledge")}
            </Button>
          ) : (
            <span className="flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground">
              <CheckCheck className="size-3.5" strokeWidth={1.5} />
              {t("activity.eventCard.read")}
            </span>
          ))}
      </div>
      <div className="mt-2">
        <ChangeRows change={event.change} type={event.type} />
      </div>
    </li>
  );
}
