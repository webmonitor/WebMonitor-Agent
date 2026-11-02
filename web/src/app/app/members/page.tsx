import type { Metadata } from "next";
import { MembersPage } from "@/features/members/members-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.members");
}

export default function MembersRoute() {
  return <MembersPage />;
}
