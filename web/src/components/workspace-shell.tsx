"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  Bell,
  LogOut,
  Menu,
  Plus,
  Radar,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useConversations, useMonitors } from "@/lib/api/hooks";
import { useAuth } from "@/lib/providers";
import { useI18n } from "@/lib/i18n";
import { useFormat } from "@/lib/format";

const CONVERSATION_PREVIEW = 8;

function ConversationList() {
  const { t } = useI18n();
  const { dayLabel, formatRelative } = useFormat();
  const conversations = useConversations();
  const params = useSearchParams();
  const pathname = usePathname();
  const active = pathname === "/app" ? params.get("conversation") : null;
  const items = conversations.data?.items ?? [];
  const [expanded, setExpanded] = useState(false);

  if (conversations.isPending) {
    return <p className="px-2 py-1 text-xs text-muted-foreground">{t("common.loading")}</p>;
  }
  if (items.length === 0) {
    return <p className="px-2 py-1 text-xs text-muted-foreground">{t("common.noConversations")}</p>;
  }

  // Keep the open conversation visible: show the newest few and keep the current one in view.
  const preview = items.slice(0, CONVERSATION_PREVIEW);
  const current = items.find((conversation) => conversation.id === active);
  const visible =
    !expanded && current && !preview.some((item) => item.id === current.id)
      ? [...preview, current]
      : expanded
        ? items
        : preview;

  const groups: { day: string; items: typeof visible }[] = [];
  for (const conversation of visible) {
    const day = dayLabel(conversation.updated_at);
    const bucket = groups.at(-1);
    if (bucket && bucket.day === day) bucket.items.push(conversation);
    else groups.push({ day, items: [conversation] });
  }

  return (
    <>
    {groups.map((group) => (
      <div key={group.day} className="mb-1">
        <p className="px-2.5 pb-0.5 pt-1 text-[10px] font-medium tracking-wide text-muted-foreground">{group.day}</p>
        <ul className="space-y-0.5">
      {group.items.map((conversation) => {
        const current = conversation.id === active;
        return (
          <li key={conversation.id}>
            <Link
              href={`/app?conversation=${conversation.id}`}
              aria-current={current ? "page" : undefined}
              className={`flex flex-col rounded-lg px-2.5 py-1.5 transition-colors ${
                current ? "bg-accent text-accent-foreground" : "hover:bg-muted"
              }`}
            >
              <span className="truncate text-[13px] leading-5">
                {conversation.title?.trim() || t("common.untitledConversation")}
              </span>
              <span className="text-[11px] leading-4 text-muted-foreground">
                {formatRelative(conversation.updated_at)}
              </span>
            </Link>
          </li>
        );
      })}
        </ul>
      </div>
    ))}
    {items.length > CONVERSATION_PREVIEW && (
      <button
        className="mt-1 w-full rounded-lg px-2.5 py-1 text-left text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? t("common.collapse") : t("common.allConversations", { count: items.length })}
      </button>
    )}
    </>
  );
}

function MonitorList({ onNavigate }: { onNavigate: () => void }) {
  const { t } = useI18n();
  const { formatInterval } = useFormat();
  const monitors = useMonitors();
  const pathname = usePathname();
  const items = monitors.data?.items ?? [];

  if (monitors.isPending) {
    return <p className="px-2 py-1 text-xs text-muted-foreground">{t("common.loading")}</p>;
  }
  if (items.length === 0) {
    return <p className="px-2 py-1 text-xs text-muted-foreground">{t("common.noMonitors")}</p>;
  }
  return (
    <ul className="space-y-0.5">
      {items.map((monitor) => {
        const active = pathname === `/app/monitors/${monitor.id}`;
        return (
          <li key={monitor.id}>
            <Link
              href={`/app/monitors/${monitor.id}`}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 transition-colors ${
                active ? "bg-accent text-accent-foreground" : "hover:bg-muted"
              }`}
            >
              <span
                aria-hidden
                className={`size-1.5 shrink-0 rounded-full ${
                  monitor.status === "active" ? "bg-success" : "bg-muted-foreground/50"
                }`}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] leading-5">{monitor.name}</span>
                <span className="block truncate text-[11px] leading-4 text-muted-foreground">
                  {monitor.status === "active" ? formatInterval(monitor.interval_seconds) : t("common.paused")}
                </span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function SectionLabel({
  children,
  count,
}: {
  children: ReactNode;
  count?: number;
}) {
  return (
    <div className="flex items-center justify-between gap-2 px-2 pb-1 pt-2 text-[11px] font-medium tracking-wide text-muted-foreground">
      <span>{children}</span>
      {typeof count === "number" && <span className="tabular-nums">{count}</span>}
    </div>
  );
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { user, isPending, error, logout, refresh } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const monitors = useMonitors();

  const links = [
    { href: "/app/events", label: t("common.events"), icon: Activity },
    { href: "/app/notifications", label: t("common.notifications"), icon: Bell },
  ];

  useEffect(() => {
    if (!isPending && !user && !error) {
      router.replace(`/login?returnTo=${encodeURIComponent(pathname)}`);
    }
  }, [isPending, user, error, router, pathname]);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  async function startConversation() {
    setOpen(false);
    // A draft only becomes a conversation once its first message is sent.
    router.push("/app?new=1");
  }

  if (isPending) {
    return (
      <main className="grid min-h-dvh place-items-center text-sm text-muted-foreground" role="status">
        {t("common.opening")}
      </main>
    );
  }
  if (!user) {
    return (
      <main className="grid min-h-dvh place-items-center p-6 text-center">
        {error ? (
          <div className="space-y-3">
            <h1 className="text-lg font-semibold">{t("common.unavailable")}</h1>
            <p className="text-sm text-error" role="alert">
              {t("common.connectionError")}
            </p>
            <Button onClick={() => void refresh()}>{t("common.reconnect")}</Button>
          </div>
        ) : (
          <p role="status" className="text-sm text-muted-foreground">
            {t("common.redirecting")}
          </p>
        )}
      </main>
    );
  }

  const initial = (user.display_name || user.email).slice(0, 1).toUpperCase();
  const section = pathname === "/app"
    ? t("common.conversations")
    : pathname.startsWith("/app/events")
      ? t("common.events")
      : pathname.startsWith("/app/notifications")
        ? t("common.notifications")
        : t("common.monitors");

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {open && (
        <button
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
          aria-label={t("common.closeNavigation")}
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[17.5rem] shrink-0 flex-col border-r bg-card transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center justify-between gap-2 px-4">
          <Link href="/app" className="flex items-center gap-2 text-[15px] font-semibold">
            <Radar className="size-5 text-primary" />
            WebMonitor
          </Link>
          <LanguageSwitcher />
          <Button
            variant="ghost"
            size="icon"
            className="size-8 md:hidden"
            aria-label={t("common.closeNavigation")}
            onClick={() => setOpen(false)}
          >
            <X className="size-4" />
          </Button>
        </div>

        <nav className="space-y-0.5 px-3 pb-2">
          <button
            onClick={() => void startConversation()}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Plus className="size-4" />
            {t("common.newConversation")}
          </button>
          {links.map(({ href, label, icon: Icon }) => {
            const current = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={current ? "page" : undefined}
                className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] transition-colors ${
                  current
                    ? "bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto border-t px-3 pb-4">
          <SectionLabel count={monitors.data?.total}>{t("common.monitors")}</SectionLabel>
          <MonitorList onNavigate={() => setOpen(false)} />
          <SectionLabel>{t("common.conversations")}</SectionLabel>
          <Suspense fallback={null}>
            <ConversationList />
          </Suspense>
        </div>

        <div className="flex items-center gap-2 border-t px-3 py-2.5">
          <span
            aria-hidden
            className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground"
          >
            {initial}
          </span>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[13px] font-medium">{user.display_name}</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {user.role === "admin" ? t("common.admin") : t("common.member")}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="size-8 text-muted-foreground"
            aria-label={t("common.logout")}
            onClick={() => void logout()}
          >
            <LogOut className="size-4" />
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b bg-card px-4 md:hidden">
          <Button variant="ghost" size="icon" aria-label={t("common.openNavigation")} onClick={() => setOpen(true)}>
            <Menu className="size-4" />
          </Button>
          <span className="flex items-center gap-1.5 text-sm font-semibold">
            <Radar className="size-4 text-primary" />
            WebMonitor
          </span>
          <span className="truncate text-sm text-muted-foreground">
            {section}
          </span>
          <LanguageSwitcher className="ml-auto" />
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
