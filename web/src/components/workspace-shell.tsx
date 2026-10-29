"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Activity, Bell, LogOut, Menu, MessageSquarePlus, Radio, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useConversations, useCreateConversation } from "@/lib/api/hooks";
import { useAuth } from "@/lib/providers";
import { formatTime } from "@/lib/format";

const links = [
  { href: "/app", label: "工作台", icon: MessageSquarePlus },
  { href: "/app/events", label: "变化事件", icon: Activity },
  { href: "/app/notifications", label: "通知与投递", icon: Bell },
];

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const { user, isPending, error, logout, refresh } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const conversations = useConversations();
  const create = useCreateConversation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!isPending && !user && !error) {
      router.replace(`/login?returnTo=${encodeURIComponent(pathname)}`);
    }
  }, [isPending, user, error, router, pathname]);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  async function startConversation() {
    const conversation = await create.mutateAsync(undefined);
    router.push(`/app?conversation=${conversation.id}`);
  }

  if (isPending) {
    return (
      <main className="grid min-h-dvh place-items-center text-sm text-muted-foreground" role="status">
        正在恢复会话…
      </main>
    );
  }
  if (!user) {
    return (
      <main className="grid min-h-dvh place-items-center p-6 text-center">
        {error ? (
          <div className="space-y-3">
            <h1>暂时无法加载工作台</h1>
            <p className="text-sm text-error" role="alert">{error.message}</p>
            <Button onClick={() => void refresh()}>重新连接</Button>
          </div>
        ) : (
          <p role="status" className="text-sm text-muted-foreground">正在前往登录…</p>
        )}
      </main>
    );
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {open && (
        <button
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
          aria-label="关闭导航遮罩"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r bg-card transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
          <Link href="/app" className="flex items-center gap-2 font-semibold">
            <Radio className="size-5 text-primary" />
            观测
          </Link>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="关闭导航" onClick={() => setOpen(false)}>
            <X />
          </Button>
        </div>

        <div className="flex flex-col gap-1 px-3 py-3">
          <Button onClick={() => void startConversation()} disabled={create.isPending} className="justify-start">
            <MessageSquarePlus />
            新对话
          </Button>
          {links.map(({ href, label, icon: Icon }) => {
            const current = href === "/app" ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                  current ? "bg-accent text-accent-foreground font-medium" : "hover:bg-muted"
                }`}
                aria-current={current ? "page" : undefined}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto border-t px-3 py-3">
          <p className="px-2 pb-2 text-xs font-medium tracking-wide text-muted-foreground">对话</p>
          <ul className="space-y-1">
            {(conversations.data?.items ?? []).map((conversation) => (
              <li key={conversation.id}>
                <Link
                  href={`/app?conversation=${conversation.id}`}
                  className="block truncate rounded-lg px-3 py-2 text-sm hover:bg-muted"
                >
                  <span className="block truncate">{conversation.title ?? "未命名对话"}</span>
                  <span className="text-xs text-muted-foreground">{formatTime(conversation.updated_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
          {conversations.data && conversations.data.items.length === 0 && (
            <p className="px-2 py-4 text-sm text-muted-foreground">还没有对话。描述你想监控的页面即可开始。</p>
          )}
        </div>

        <div className="flex items-center gap-2 border-t px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{user.display_name}</p>
            <p className="truncate text-xs text-muted-foreground">{user.role === "admin" ? "管理员" : "成员"}</p>
          </div>
          <Button variant="ghost" size="icon" aria-label="退出登录" onClick={() => void logout()}>
            <LogOut />
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b bg-card px-4 py-2 md:hidden">
          <Button variant="ghost" size="icon" aria-label="打开导航" onClick={() => setOpen(true)}>
            <Menu />
          </Button>
          <span className="font-semibold">观测</span>
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
