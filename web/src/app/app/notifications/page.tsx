import { localizedMetadata } from "@/lib/i18n/server";
import { NotificationsPage } from "@/features/notifications/notifications-page";

export function generateMetadata() {
  return localizedMetadata("common.title.notifications");
}

export default function NotificationsRoute() {
  return <NotificationsPage />;
}
