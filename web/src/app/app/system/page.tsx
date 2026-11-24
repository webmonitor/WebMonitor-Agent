import type { Metadata } from "next";
import { SystemPage } from "@/features/system/system-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("system.title");
}

export default function SystemRoute() {
  return <SystemPage />;
}
