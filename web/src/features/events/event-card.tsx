"use client";
import Link from "next/link";
import { Check, CheckCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { EventView } from "@/lib/api/hooks";
import { eventLabel, fieldLabel, formatTime, formatValue } from "@/lib/format";

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

/** before → after, one row per field, using the labels stored with the event. */
export function ChangeRows({
  change,
  type,
}: {
  change: Record<string, unknown>;
  type?: string;
}) {
  if (type === "run_failed") {
    return <p className="text-[13px] text-muted-foreground">这次采集没有成功，监控继续使用上一次采集到的内容。</p>;
  }
  if (type === "recovered") {
    return <p className="text-[13px] text-muted-foreground">采集恢复正常，监控重新开始比较内容。</p>;
  }
  const labels = (change.labels ?? {}) as Record<string, string>;
  const rows = differencesOf(change);
  if (rows.length === 0) {
    return <p className="text-[13px] text-muted-foreground">内容发生变化，但没有可对照的字段。</p>;
  }
  return (
    <ul className="space-y-1.5">
      {rows.map((row, index) => (
        <li key={`${row.field ?? index}-${index}`} className="text-[13px]">
          <span className="text-muted-foreground">
            {fieldLabel({ name: row.field ?? "", semantic: labels[row.field ?? ""] })}
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 tabular-nums">
            <span className="text-muted-foreground/80 line-through decoration-border">
              {formatValue(row.before)}
            </span>
            <span aria-hidden className="text-muted-foreground/60">→</span>
            <span className="font-medium">{formatValue(row.after)}</span>
          </span>
        </li>
      ))}
    </ul>
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
  const unread = !event.acknowledged_at;
  return (
    <li className={`surface-pad space-y-2.5 ${unread ? "border-l-2 border-l-primary/60" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TONES[event.type] ?? "neutral"}>{eventLabel(event.type)}</Badge>
            <Link
              href={`/app/monitors/${event.monitor_id}`}
              className="truncate text-[13px] font-medium hover:underline"
            >
              {event.monitor_name}
            </Link>
          </div>
          <p className="meta">{formatTime(event.created_at)}</p>
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
              <Check className="size-3.5" />
              标为已读
            </Button>
          ) : (
            <span className="flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground">
              <CheckCheck className="size-3.5" />
              已读
            </span>
          ))}
      </div>
      <ChangeRows change={event.change} type={event.type} />
    </li>
  );
}
