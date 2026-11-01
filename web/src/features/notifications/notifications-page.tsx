"use client";
import { DeliveriesPanel } from "@/features/notifications/deliveries-panel";
import { GroupsPanel } from "@/features/notifications/groups-panel";
import { PageBody, PageHeader } from "@/components/page-header";
import { useI18n } from "@/lib/i18n";

export function NotificationsPage() {
  const { t } = useI18n();
  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title={t("activity.notifications.title")}
          description={t("activity.notifications.description")}
        />
        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-14">
          <GroupsPanel />
          <DeliveriesPanel />
        </div>
      </PageBody>
    </div>
  );
}
