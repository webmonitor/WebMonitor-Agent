import type { Metadata } from "next";
import { Providers } from "@/lib/providers";
import "./globals.css";

export const metadata: Metadata = { title: { default: "WebMonitor · 网页变化监控", template: "%s · WebMonitor" }, description: "WebMonitor 定期检查网页中的价格、库存和公告。通过对话创建监控，设置通知条件，在发现相应变化时接收邮件，并查看更新前后的内容。", referrer: "no-referrer" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="zh-CN"><body><Providers>{children}</Providers></body></html>;
}
