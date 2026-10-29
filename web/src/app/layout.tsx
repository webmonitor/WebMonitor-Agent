import type { Metadata } from "next";
import { Providers } from "@/lib/providers";
import "./globals.css";

export const metadata: Metadata = { title: { default: "WebMonitor · 网页变化监控", template: "%s · WebMonitor" }, description: "用一句话描述要监控的网页，确认一次真实预览后再开始。变化、证据与邮件记录都留在工作台里。", referrer: "no-referrer" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="zh-CN"><body><Providers>{children}</Providers></body></html>;
}
