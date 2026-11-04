"use client";
import { useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PageBody, PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Select } from "@/components/ui/select";
import { useAckEvent, useEvents, useMonitors, useUnreadEventCount } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { EventCard } from "@/features/events/event-card";
import { ListPagination } from "@/components/list-pagination";

type Filter = "all" | "unread";

const FILTERS: Filter[] = ["all", "unread"];

const EVENT_TYPES = ["content_changed", "list_changed", "run_failed", "recovered"] as const;

export function EventsPage() {
  const { t } = useI18n();
  const { dayLabel, eventLabel, errorText } = useFormat();
  const params = useSearchParams();
  const router = useRouter();
  const filter: Filter = params.get("unread") === "1" ? "unread" : "all";
  const monitorId = params.get("monitor") ?? "";
  const eventType = params.get("type") ?? "";
  const events = useEvents(
    monitorId || undefined,
    eventType || undefined,
    filter === "unread" ? false : undefined,
  );
  const unread = useUnreadEventCount();
  const monitors = useMonitors();
  const acknowledge = useAckEvent();

  const visible = events.data?.items ?? [];
  const total = events.data?.total ?? 0;
  const unreadCount = unread.data ?? 0;

  // The address is the filter state, so a shared or reloaded link shows the same list.
  function setParam(name: string, value: string | null) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(name, value);
    else next.delete(name);
    const query = next.toString();
    router.replace(query ? `/app/events?${query}` : "/app/events");
  }

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
            <div className="flex flex-wrap items-center gap-2">
              <Select
                label={t("activity.events.filter.monitor")}
                value={monitorId}
                placeholder={t("activity.events.filter.allMonitors")}
                onChange={(value) => setParam("monitor", value)}
                className="w-40"
                options={[
                  { value: "", label: t("activity.events.filter.allMonitors") },
                  ...(monitors.data?.items ?? []).map((monitor) => ({
                    value: monitor.id,
                    label: monitor.name,
                  })),
                ]}
              />
              <Select
                label={t("activity.events.filter.type")}
                value={eventType}
                placeholder={t("activity.events.filter.allTypes")}
                onChange={(value) => setParam("type", value)}
                className="w-36"
                options={[
                  { value: "", label: t("activity.events.filter.allTypes") },
                  ...EVENT_TYPES.map((value) => ({ value, label: eventLabel(value) })),
                ]}
              />
              <span className="inline-flex items-center gap-0.5">
                {FILTERS.map((value) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={filter === value}
                    className={`h-8 rounded-md px-2.5 text-[13px] transition-colors duration-150 ${
                      filter === value
                        ? "bg-surface-card font-medium text-ink"
                        : "text-muted-foreground hover:text-ink"
                    }`}
                    onClick={() => setParam("unread", value === "unread" ? "1" : null)}
                  >
                    {value === "unread"
                      ? unreadCount
                        ? t("activity.events.filter.unreadCount", { count: unreadCount })
                        : t("activity.events.filter.unread")
                      : t("activity.events.filter.all")}
                  </button>
                ))}
              </span>
            </div>
          }
        />
        {acknowledge.error && <p className="text-sm text-error" role="alert">{errorText(acknowledge.error)}</p>}

        {events.isPending && <p className="meta">{t("activity.events.loading")}</p>}
        {events.error && (
          <p className="text-sm text-error" role="alert">
            {t("activity.events.error")}
          </p>
        )}

        {!events.isPending && !events.error && total === 0 && (
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

        <div className="space-y-12">
          {groups.map((group) => (
            <section key={group.day}>
              <h2 className="eyebrow border-b border-hairline pb-2">{group.day}</h2>
              <ul className="divide-y">
                {group.events.map((event) => (
                  <EventCard
                    key={event.id}
                    event={event}
                    onAcknowledge={(id) => acknowledge.mutate(id)}
                    acknowledging={acknowledge.isPending}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
        <ListPagination query={events} />
      </PageBody>
    </div>
  );
}
