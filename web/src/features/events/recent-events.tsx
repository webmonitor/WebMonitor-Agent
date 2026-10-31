"use client";
import Link from "next/link";
import { useEvents } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { ChangeRows } from "@/features/events/event-card";

/** The three latest events for the monitor created in this conversation. */
export function RecentEvents({ monitorId }: { monitorId: string }) {
  const { t } = useI18n();
  const { eventLabel, formatTime } = useFormat();
  const events = useEvents(monitorId);
  const items = (events.data?.items ?? [])
    .filter((event) => event.monitor_id === monitorId)
    .slice(0, 3);

  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{t("activity.recent.title")}</h2>
        <Link href="/app/events" className="text-xs text-primary underline-offset-2 hover:underline">
          {t("activity.recent.all")}
        </Link>
      </div>
      {items.length === 0 ? (
        <p className="meta">{t("activity.recent.empty")}</p>
      ) : (
        <ul className="space-y-2">
          {items.map((event) => (
            <li key={event.id} className="surface space-y-1.5 p-3">
              <p className="flex items-baseline justify-between gap-2 text-[11px] text-muted-foreground">
                <span>{eventLabel(event.type)}</span>
                <span>{formatTime(event.created_at)}</span>
              </p>
              <ChangeRows change={event.change} type={event.type} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
