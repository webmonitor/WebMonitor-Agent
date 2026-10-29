import type { Metadata } from "next";
import { WorkspaceShell } from "@/components/workspace-shell";
import { localizedMetadata } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { title } = await localizedMetadata("common.title.workspace");
  return { title: { default: String(title), template: "%s · WebMonitor" } };
}

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <WorkspaceShell>{children}</WorkspaceShell>;
}
