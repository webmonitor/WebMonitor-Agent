"use client";
import { useMemo, useState } from "react";
import { PageBody, PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { useAckEvent, useEvents } from "@/lib/api/hooks";
import { dayLabel } from "@/lib/format";
import { EventCard } from "@/features/events/event-card";

type Filter = "all" | "unread";

export function EventsPage() {
  const events = useEvents();
  const acknowledge = useAckEvent();
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
  }, [visible]);

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title="事件"
          description="监控发现变化、采集失败或恢复时都会记录在这里。新监控的第一次成功采集用来建立基线，从第二次采集开始比较变化。"
          actions={
            <div className="flex items-center gap-1 rounded-lg border bg-card p-0.5">
              {([
                ["all", "全部"],
                ["unread", unreadCount ? `未读 ${unreadCount}` : "未读"],
              ] as const).map(([value, label]) => (
                <Button
                  key={value}
                  size="sm"
                  variant={filter === value ? "secondary" : "ghost"}
                  className="h-7 px-2.5 text-xs"
                  onClick={() => setFilter(value)}
                >
                  {label}
                </Button>
              ))}
            </div>
          }
        />

        {events.isPending && <p className="meta">正在加载…</p>}
        {events.error && (
          <p className="text-sm text-error" role="alert">
            事件加载失败，请刷新页面重试。
          </p>
        )}

        {!events.isPending && visible.length === 0 && (
          <EmptyState
            title={filter === "unread" ? "没有未读事件" : "还没有事件"}
            description={
              filter === "unread"
                ? "所有事件都已标记为已读。"
                : "监控开始按计划采集后，发生变化时会在这里出现。"
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
