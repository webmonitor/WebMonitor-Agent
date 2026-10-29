import type { Metadata } from "next";
import { MonitorPage } from "@/features/monitors/monitor-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.monitor");
}

export default async function MonitorRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MonitorPage monitorId={id} />;
}
