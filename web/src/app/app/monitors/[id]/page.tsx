import { MonitorPage } from "@/features/monitors/monitor-page";

export default async function MonitorRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MonitorPage monitorId={id} />;
}
