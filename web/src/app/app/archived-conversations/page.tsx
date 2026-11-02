import type { Metadata } from "next";
import { ArchivedConversationsPage } from "@/features/chat/archived-conversations-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("chat.archive.title");
}

export default function ArchivedConversationsRoute() {
  return <ArchivedConversationsPage />;
}
