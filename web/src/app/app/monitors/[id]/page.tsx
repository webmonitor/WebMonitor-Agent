import type { Metadata } from "next";
import { MonitorPage } from "@/features/monitors/monitor-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.monitor");
}

export default async function MonitorRoute({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ job?: string }>;
}) {
  const { id } = await params;
  const { job } = await searchParams;
  return <MonitorPage monitorId={id} initialJob={job ?? null} />;
}
