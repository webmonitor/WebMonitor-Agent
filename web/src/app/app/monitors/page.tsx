import type { Metadata } from "next";
import { MonitorsPage } from "@/features/monitors/monitors-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.monitors");
}

export default function MonitorsRoute() {
  return <MonitorsPage />;
}
