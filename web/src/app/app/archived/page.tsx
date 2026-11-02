import type { Metadata } from "next";
import { ArchivedPage } from "@/features/monitors/archived-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.archived");
}

export default function ArchivedRoute() {
  return <ArchivedPage />;
}
