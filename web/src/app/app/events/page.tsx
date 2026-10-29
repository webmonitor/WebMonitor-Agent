import { localizedMetadata } from "@/lib/i18n/server";
import { EventsPage } from "@/features/events/events-page";

export function generateMetadata() {
  return localizedMetadata("common.title.events");
}

export default function EventsRoute() {
  return <EventsPage />;
}
