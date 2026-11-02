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
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useConversations, useMonitors } from "@/lib/api/hooks";
import { useAuth } from "@/lib/providers";
import { useI18n } from "@/lib/i18n";
import { useFormat } from "@/lib/format";
import { ListPagination } from "@/components/list-pagination";

const CONVERSATION_PREVIEW = 8;

/* One row height for every navigation item, so the sidebar reads as a column. */
const ROW = "flex h-8 items-center gap-2 rounded-md px-2 text-[13px] transition-colors duration-150";

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
  if (conversations.error && items.length === 0) return <ListPagination query={conversations} />;
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
        <div key={group.day} className="mt-2 first:mt-0">
          {/* Day captions sit closer to their own rows than to the group above. */}
          <p className="num px-2 pb-1 text-[11px] leading-4 text-muted-foreground">{group.day}</p>
          <ul>
            {group.items.map((conversation) => {
              const isCurrent = conversation.id === active;
              return (
                <li key={conversation.id}>
                  <Link
                    href={`/app?conversation=${conversation.id}`}
                    aria-current={isCurrent ? "page" : undefined}
                    className={`${ROW} ${
                      isCurrent
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {conversation.title?.trim() || t("common.untitledConversation")}
                    </span>
                    <span className="num shrink-0 text-[11px] text-muted-foreground">
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
          className="mt-1 h-7 px-2 text-left text-[11px] text-muted-foreground transition-colors duration-150 hover:text-foreground"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? t("common.collapse") : t("common.allConversations", { count: items.length })}
        </button>
      )}
      {expanded && <ListPagination query={conversations} />}
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
  if (monitors.error && items.length === 0) return <ListPagination query={monitors} />;
  if (items.length === 0) {
    return <p className="px-2 py-1 text-xs text-muted-foreground">{t("common.noMonitors")}</p>;
  }
  return (
    <>
      <ul>
        {items.map((monitor) => {
          const active = pathname === `/app/monitors/${monitor.id}`;
          const live = monitor.status === "active";
          return (
            <li key={monitor.id}>
              <Link
                href={`/app/monitors/${monitor.id}`}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={`${ROW} pr-2 ${
                  active
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                {/* The signature: one dot that is green only while the monitor is live. */}
                <span
                  aria-hidden
                  className={`size-1.5 shrink-0 rounded-full ${live ? "bg-success" : "bg-muted-foreground/40"}`}
                />
                <span className="min-w-0 flex-1 truncate text-foreground">{monitor.name}</span>
                <span className="num shrink-0 text-[11px] text-muted-foreground">
                  {live ? formatInterval(monitor.interval_seconds) : t("common.paused")}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <ListPagination query={monitors} />
    </>
  );
}

function SectionLabel({
  children,
  count,
  action,
}: {
  children: ReactNode;
  count?: number;
  action?: ReactNode;
}) {
  return (
    <div className="mt-6 flex items-baseline justify-between gap-2 px-2 pb-1 first:mt-0">
      <span className="text-[11px] leading-4 font-medium text-foreground/70">{children}</span>
      <span className="flex items-center gap-2">
        {typeof count === "number" && (
          <span className="num text-[11px] text-muted-foreground">{count}</span>
        )}
        {action}
      </span>
    </div>
  );
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { user, isPending, error, logout, refresh } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<Error | null>(null);
  const { errorText } = useFormat();
  const monitors = useMonitors();

  const links = [
    { href: "/app/events", label: t("common.events"), icon: Activity },
    { href: "/app/notifications", label: t("common.notifications"), icon: Bell },
    ...(user?.role === "admin"
      ? [{ href: "/app/members", label: t("common.members"), icon: Users }]
      : []),
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
            <h1 className="text-lg font-medium">{t("common.unavailable")}</h1>
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
        : pathname.startsWith("/app/members")
          ? t("common.members")
          : pathname.startsWith("/app/archived")
            ? t("common.archived")
            : t("common.monitors");

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {open && (
        <button
          className="fixed inset-0 z-30 bg-[rgba(30,27,22,0.28)] md:hidden"
          aria-label={t("common.closeNavigation")}
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[17.5rem] shrink-0 flex-col border-r bg-card transition-transform duration-200 md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center gap-2 px-3">
          <Link href="/app" className="flex min-w-0 items-center gap-2 text-[15px] font-medium">
            <Radar className="size-4 text-primary" strokeWidth={1.5} />
            <span className="truncate">WebMonitor</span>
          </Link>
          <LanguageSwitcher className="ml-auto" />
          <Button
            variant="ghost"
            size="icon"
            className="size-7 md:hidden"
            aria-label={t("common.closeNavigation")}
            onClick={() => setOpen(false)}
          >
            <X className="size-4" strokeWidth={1.5} />
          </Button>
        </div>

        <nav className="space-y-0.5 px-2 pb-2">
          <button
            onClick={() => void startConversation()}
            className={`${ROW} w-full text-left text-muted-foreground hover:bg-muted hover:text-foreground`}
          >
            <Plus className="size-4" strokeWidth={1.5} />
            {t("common.newConversation")}
          </button>
          {links.map(({ href, label, icon: Icon }) => {
            const current = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={current ? "page" : undefined}
                className={`${ROW} ${
                  current
                    ? "bg-secondary font-medium text-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon className="size-4" strokeWidth={1.5} />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto border-t px-2 pt-3 pb-4">
          <SectionLabel
            count={monitors.data?.total}
            action={
              <Link
                href="/app/archived"
                className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                {t("common.archived")}
              </Link>
            }
          >
            {t("common.monitors")}
          </SectionLabel>
          <MonitorList onNavigate={() => setOpen(false)} />
          <SectionLabel>{t("common.conversations")}</SectionLabel>
          <Suspense fallback={null}>
            <ConversationList />
          </Suspense>
        </div>

        <div className="flex h-14 items-center gap-2 border-t px-3">
          <span
            aria-hidden
            className="grid size-7 shrink-0 place-items-center rounded-full border text-[11px] font-medium text-muted-foreground"
          >
            {initial}
          </span>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[12px] font-medium">{user.display_name}</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {user.role === "admin" ? t("common.admin") : t("common.member")}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="size-7 text-muted-foreground"
            aria-label={t("common.logout")}
            onClick={() => { setLogoutError(null); void logout().catch(setLogoutError); }}
          >
            <LogOut className="size-4" strokeWidth={1.5} />
          </Button>
        </div>
        {logoutError && <p role="alert" className="px-3 pb-2 text-xs text-error">{errorText(logoutError)}</p>}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b bg-card px-4 md:hidden">
          <Button variant="ghost" size="icon" className="size-8" aria-label={t("common.openNavigation")} onClick={() => setOpen(true)}>
            <Menu className="size-4" strokeWidth={1.5} />
          </Button>
          <span className="flex items-center gap-1.5 text-sm font-medium">
            <Radar className="size-4 text-primary" strokeWidth={1.5} />
            WebMonitor
          </span>
          <span className="truncate text-[13px] text-muted-foreground">
            {section}
          </span>
          <LanguageSwitcher className="ml-auto" />
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
