import { DeliveriesPanel } from "@/features/notifications/deliveries-panel";
import { GroupsPanel } from "@/features/notifications/groups-panel";
import { PageBody, PageHeader } from "@/components/page-header";

export const metadata = { title: "通知" };

export default function NotificationsRoute() {
  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title="通知"
          description="通知组决定谁收到邮件；投递记录保存每一封邮件的去向与结果。"
        />
        <div className="grid items-start gap-8 lg:grid-cols-2">
          <GroupsPanel />
          <DeliveriesPanel />
        </div>
      </PageBody>
    </div>
  );
}
