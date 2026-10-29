"use client";
import { useMemo, useState } from "react";
import { PageBody, PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { useAckEvent, useEvents } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { EventCard } from "@/features/events/event-card";

type Filter = "all" | "unread";

const FILTERS: Filter[] = ["all", "unread"];

export function EventsPage() {
  const events = useEvents();
  const acknowledge = useAckEvent();
  const { t } = useI18n();
  const { dayLabel } = useFormat();
  const [filter, setFilter] = useState<Filter>("all");

  const items = events.data?.items ?? [];
  const unreadCount = items.filter((event) => !event.acknowledged_at).length;
  const visible = filter === "unread" ? items.filter((event) => !event.acknowledged_at) : items;

  const groups = useMemo(() => {
    const buckets: { day: string; events: typeof visible }[] = [];
    for (const event of visible) {
      const day = dayLabel(event.created_at);
      const bucket = buckets.at(-1);
      if (bucket && bucket.day === day) bucket.events.push(event);
      else buckets.push({ day, events: [event] });
    }
    return buckets;
  }, [visible, dayLabel]);

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title={t("activity.events.title")}
          description={t("activity.events.description")}
          actions={
            <div className="flex items-center gap-1 rounded-lg border bg-card p-0.5">
              {FILTERS.map((value) => (
                <Button
                  key={value}
                  size="sm"
                  variant={filter === value ? "secondary" : "ghost"}
                  className="h-7 px-2.5 text-xs"
                  onClick={() => setFilter(value)}
                >
                  {value === "unread"
                    ? unreadCount
                      ? t("activity.events.filter.unreadCount", { count: unreadCount })
                      : t("activity.events.filter.unread")
                    : t("activity.events.filter.all")}
                </Button>
              ))}
            </div>
          }
        />

        {events.isPending && <p className="meta">{t("activity.events.loading")}</p>}
        {events.error && (
          <p className="text-sm text-error" role="alert">
            {t("activity.events.error")}
          </p>
        )}

        {!events.isPending && visible.length === 0 && (
          <EmptyState
            title={
              filter === "unread"
                ? t("activity.events.empty.unreadTitle")
                : t("activity.events.empty.title")
            }
            description={
              filter === "unread"
                ? t("activity.events.empty.unreadDescription")
                : t("activity.events.empty.description")
            }
          />
        )}

        <div className="max-w-3xl space-y-6">
          {groups.map((group) => (
            <section key={group.day} className="space-y-2">
              <h2 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {group.day}
              </h2>
              <ul className="space-y-2">
                {group.events.map((event) => (
                  <EventCard
                    key={event.id}
                    event={event}
                    onAcknowledge={(id) => void acknowledge.mutateAsync(id)}
                    acknowledging={acknowledge.isPending}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      </PageBody>
    </div>
  );
}
