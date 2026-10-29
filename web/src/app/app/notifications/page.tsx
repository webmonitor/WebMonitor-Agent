import { DeliveriesPanel } from "@/features/notifications/deliveries-panel";
import { GroupsPanel } from "@/features/notifications/groups-panel";

export const metadata = { title: "通知与投递" };

export default function NotificationsRoute() {
  return (
    <div className="h-full overflow-y-auto px-4 py-5">
      <h1 className="mb-4">通知与投递</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <GroupsPanel />
        <DeliveriesPanel />
      </div>
    </div>
  );
}
