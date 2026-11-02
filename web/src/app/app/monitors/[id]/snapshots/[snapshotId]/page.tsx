import type { Metadata } from "next";
import { SnapshotPage } from "@/features/monitors/snapshot-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.snapshot");
}

export default async function SnapshotRoute({
  params,
}: {
  params: Promise<{ id: string; snapshotId: string }>;
}) {
  const { id, snapshotId } = await params;
  return <SnapshotPage monitorId={id} snapshotId={snapshotId} />;
}
