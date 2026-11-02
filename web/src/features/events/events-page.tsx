"use client";
import { useMemo, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { PageBody, PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { useAckEvent, useEvents, useMonitors } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { EventCard } from "@/features/events/event-card";
import { ListPagination } from "@/components/list-pagination";

type Filter = "all" | "unread";

const FILTERS: Filter[] = ["all", "unread"];

const EVENT_TYPES = [
  "price_changed", "list_changed", "content_changed", "run_failed", "recovered",
] as const;

/**
 * A filter is one quiet control: hairline, 32px, the same chevron and focus ring
 * as every other control in the workspace.
 */
function FilterSelect({
  label,
  value,
  onChange,
  className,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span className={`relative inline-flex ${className ?? ""}`}>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 w-full appearance-none truncate rounded-md border border-input bg-card pl-2.5 pr-7 text-xs text-foreground transition-colors duration-150 hover:bg-muted focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:outline-none"
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2 text-muted-foreground"
        strokeWidth={1.5}
      />
    </span>
  );
}

export function EventsPage() {
  const { t } = useI18n();
  const { dayLabel, eventLabel, errorText } = useFormat();
  const [filter, setFilter] = useState<Filter>("all");
  const [monitorId, setMonitorId] = useState("");
  const [eventType, setEventType] = useState("");
  const events = useEvents(monitorId || undefined, eventType || undefined);
  const monitors = useMonitors();
  const acknowledge = useAckEvent();

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
            <div className="flex flex-wrap items-center gap-2">
              <FilterSelect
                label={t("activity.events.filter.monitor")}
                value={monitorId}
                onChange={setMonitorId}
                className="max-w-40"
              >
                <option value="">{t("activity.events.filter.allMonitors")}</option>
                {(monitors.data?.items ?? []).map((monitor) => (
                  <option key={monitor.id} value={monitor.id}>{monitor.name}</option>
                ))}
              </FilterSelect>
              <FilterSelect
                label={t("activity.events.filter.type")}
                value={eventType}
                onChange={setEventType}
              >
                <option value="">{t("activity.events.filter.allTypes")}</option>
                {EVENT_TYPES.map((value) => (
                  <option key={value} value={value}>{eventLabel(value)}</option>
                ))}
              </FilterSelect>
              <span className="inline-flex items-center gap-0.5">
                {FILTERS.map((value) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={filter === value}
                    className={`h-8 rounded-md px-2.5 text-xs transition-colors duration-150 ${
                      filter === value
                        ? "bg-secondary font-medium text-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    onClick={() => setFilter(value)}
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

        {!events.isPending && !events.error && visible.length === 0 && !events.hasNextPage && (
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

        <div className="space-y-10">
          {groups.map((group) => (
            <section key={group.day}>
              <h2 className="num border-b pb-1.5 text-[11px] text-muted-foreground">{group.day}</h2>
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
