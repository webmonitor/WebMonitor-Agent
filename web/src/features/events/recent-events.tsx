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
    <section>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="section-title">{t("activity.recent.title")}</h2>
        <Link href="/app/events" className="text-[11px] text-primary underline-offset-2 hover:underline">
          {t("activity.recent.all")}
        </Link>
      </div>
      {items.length === 0 ? (
        <p className="meta">{t("activity.recent.empty")}</p>
      ) : (
        <ul className="divide-y border-t">
          {items.map((event) => (
            <li key={event.id} className="space-y-1.5 py-2.5">
              <p className="flex items-baseline justify-between gap-2 text-[11px] text-muted-foreground">
                <span>{eventLabel(event.type)}</span>
                <span className="num">{formatTime(event.created_at)}</span>
              </p>
              <ChangeRows change={event.change} type={event.type} />
              <div className="flex flex-wrap gap-x-4">
                {event.snapshot_id && (
                  <Link
                    href={`/app/monitors/${monitorId}/snapshots/${event.snapshot_id}`}
                    className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                  >
                    {t("monitors.snapshot.open")}
                  </Link>
                )}
                <Link
                  href={`/app/monitors/${monitorId}?job=${event.job_id}`}
                  className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  {t("monitors.dialog.open")}
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
