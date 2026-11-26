"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Activity,
  Archive,
  Bell,
  Gauge,
  KeyRound,
  LogOut,
  Mail,
  Menu,
  Plus,
  Radar,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useArchiveConversation, useConversations, useMonitors } from "@/lib/api/hooks";
import { useAuth } from "@/lib/providers";
import { useI18n } from "@/lib/i18n";
import { useFormat } from "@/lib/format";
import { ListPagination } from "@/components/list-pagination";
import { archivedConversationRedirect } from "@/features/chat/chat-state";

const CONVERSATION_PREVIEW = 8;

/* One row height for every navigation item, so the sidebar reads as a column. */
const ROW = "flex h-9 items-center gap-2.5 rounded-lg border border-transparent px-3 text-[14px] transition-colors duration-150";

function ConversationList({ onNavigate }: { onNavigate: () => void }) {
  const { t } = useI18n();
  const { dayLabel, errorText, formatRelative } = useFormat();
  const conversations = useConversations();
  const archive = useArchiveConversation();
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();
  const active = pathname === "/app" ? params.get("conversation") : null;
  const items = conversations.data?.items ?? [];
  const [expanded, setExpanded] = useState(false);

  if (conversations.isPending) {
    return <p className="px-2.5 py-1 text-[13px] text-muted-soft">{t("common.loading")}</p>;
  }
  if (conversations.error && items.length === 0) return <ListPagination query={conversations} />;
  if (items.length === 0) {
    return <p className="px-2.5 py-1 text-[13px] text-muted-soft">{t("common.noConversations")}</p>;
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
          <p className="num px-2.5 pb-1 text-[12px] leading-4 text-muted-soft">{group.day}</p>
          <ul>
            {group.items.map((conversation) => {
              const isCurrent = conversation.id === active;
              return (
                <li key={conversation.id} className="group relative">
                  <Link
                    href={`/app?conversation=${conversation.id}`}
                    onClick={onNavigate}
                    aria-current={isCurrent ? "page" : undefined}
                    className={`${ROW} pr-8 ${
                      isCurrent
                        ? "border-hairline bg-canvas font-medium text-ink"
                        : "text-body hover:bg-surface-strong/60 hover:text-ink"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {conversation.title?.trim() || t("common.untitledConversation")}
                    </span>
                    <span className="num shrink-0 text-[12px] text-muted-soft">
                      {formatRelative(conversation.updated_at)}
                    </span>
                  </Link>
                  <button
                    type="button"
                    aria-label={t("chat.archive.action")}
                    disabled={archive.isPending}
                    className="absolute top-1/2 right-1 grid size-6 -translate-y-1/2 place-items-center rounded-md text-muted-soft transition-[color,opacity] duration-150 hover:text-ink disabled:opacity-45 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
                    onClick={() => archive.mutate(conversation.id, {
                      onSuccess: () => {
                        const destination = archivedConversationRedirect(
                          window.location.pathname,
                          window.location.search,
                          conversation.id,
                        );
                        if (destination) router.replace(destination);
                        onNavigate();
                      },
                    })}
                  >
                    <Archive className="size-3.5" strokeWidth={1.5} />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      {archive.error && (
        <p role="alert" className="px-2.5 pt-1 text-[13px] text-error">{errorText(archive.error)}</p>
      )}
      {items.length > CONVERSATION_PREVIEW && (
        <button
          className="mt-1 h-7 px-2.5 text-left text-[13px] text-muted-soft transition-colors duration-150 hover:text-ink"
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
    return <p className="px-2.5 py-1 text-[13px] text-muted-soft">{t("common.loading")}</p>;
  }
  if (monitors.error && items.length === 0) return <ListPagination query={monitors} />;
  if (items.length === 0) {
    return <p className="px-2.5 py-1 text-[13px] text-muted-soft">{t("common.noMonitors")}</p>;
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
                    ? "border-hairline bg-canvas font-medium text-ink"
                    : "text-body hover:bg-surface-strong/60 hover:text-ink"
                }`}
              >
                {/* The signature: one dot that is green only while the monitor is live. */}
                <span
                  aria-hidden
                  className={`size-1.5 shrink-0 rounded-full ${live ? "bg-success" : "bg-muted-foreground/40"}`}
                />
                <span className="min-w-0 flex-1 truncate text-ink">{monitor.name}</span>
                <span className="num shrink-0 text-[12px] text-muted-soft">
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
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mt-6 flex items-baseline justify-between gap-2 px-2.5 pb-1 first:mt-0">
      <span className="eyebrow">{children}</span>
      {action}
    </div>
  );
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { user, isPending, error, logout, refresh } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [compact, setCompact] = useState(false);
  const [logoutError, setLogoutError] = useState<Error | null>(null);
  const navigation = useRef<HTMLElement>(null);
  const { errorText } = useFormat();

  const links = [
    { href: "/app/monitors", label: t("common.monitors"), icon: Radar },
    { href: "/app/events", label: t("common.events"), icon: Activity },
    { href: "/app/notifications", label: t("common.notifications"), icon: Bell },
    { href: "/app/templates", label: t("common.templates"), icon: Mail },
    { href: "/app/tokens", label: t("common.tokens"), icon: KeyRound },
    ...(user?.role === "admin"
      ? [
          { href: "/app/members", label: t("common.members"), icon: Users },
          { href: "/app/system", label: t("system.title"), icon: Gauge },
        ]
      : []),
  ];

  useEffect(() => {
    if (!isPending && !user && !error) {
      const returnTo = window.location.pathname + window.location.search + window.location.hash;
      router.replace(`/login?returnTo=${encodeURIComponent(returnTo)}`);
    }
  }, [isPending, user, error, router]);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!compact || !open || !navigation.current) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = navigation.current;
    const focusable = () => Array.from(
      panel.querySelectorAll<HTMLElement>("a[href], button:not(:disabled)"),
    ).filter((element) => element.getClientRects().length > 0);
    focusable()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      const first = items[0];
      const last = items.at(-1);
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
  }, [compact, open]);

  async function startConversation() {
    setOpen(false);
    // A draft only becomes a conversation once its first message is sent.
    router.push("/app?new=1");
  }

  if (isPending) {
    return (
      <main className="grid min-h-dvh place-items-center t-body-sm text-muted-foreground" role="status">
        {t("common.opening")}
      </main>
    );
  }
  if (!user) {
    return (
      <main className="grid min-h-dvh place-items-center p-6 text-center">
        {error ? (
          <div className="space-y-3">
            <h1 className="display-sm">{t("common.unavailable")}</h1>
            <p className="t-body-sm text-error" role="alert">
              {t("common.connectionError")}
            </p>
            <Button onClick={() => void refresh()}>{t("common.reconnect")}</Button>
          </div>
        ) : (
          <p role="status" className="t-body-sm text-muted-foreground">
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
        : pathname.startsWith("/app/tokens")
          ? t("common.tokens")
          : pathname.startsWith("/app/system")
            ? t("system.title")
        : pathname.startsWith("/app/templates")
          ? t("common.title.templates")
        : pathname.startsWith("/app/members")
          ? t("common.members")
          : pathname.startsWith("/app/archived-conversations")
            ? t("chat.archive.title")
            : pathname.startsWith("/app/archived")
              ? t("common.archived")
              : t("common.monitors");

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      <a
        href="#workspace-main"
        className="fixed top-3 left-3 z-[60] -translate-y-24 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground shadow-soft transition-transform focus:translate-y-0"
      >
        {t("common.skipToContent")}
      </a>
      {open && (
        <button
          className="fixed inset-0 z-30 bg-[rgba(20,20,19,0.32)] md:hidden"
          aria-label={t("common.closeNavigation")}
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        ref={navigation}
        id="workspace-navigation"
        aria-label={t("public.nav.aria")}
        role={compact ? "dialog" : undefined}
        aria-modal={compact && open ? true : undefined}
        inert={compact && !open}
        className={`fixed inset-y-0 left-0 z-40 flex w-[17.5rem] shrink-0 flex-col border-r border-hairline bg-surface-soft transition-transform duration-200 ease-[var(--ease)] md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 items-center gap-2 px-3">
          <Link href="/app" className="flex min-w-0 items-center gap-2.5 font-display text-[20px] leading-none tracking-[-0.02em] text-ink">
            <Radar className="size-[18px] text-primary" strokeWidth={1.5} />
            <span className="truncate">WebMonitor</span>
          </Link>
          <span className="ml-auto hidden md:block">
            <LanguageSwitcher />
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto size-7 md:hidden"
            aria-label={t("common.closeNavigation")}
            onClick={() => setOpen(false)}
          >
            <X className="size-4" strokeWidth={1.5} />
          </Button>
        </div>

        <nav className="space-y-0.5 px-2 pb-2">
          <Button
            onClick={() => void startConversation()}
            className="mb-2 h-9 w-full justify-start px-3"
          >
            <Plus className="size-4" strokeWidth={1.5} />
            {t("common.newConversation")}
          </Button>
          {links.map(({ href, label, icon: Icon }) => {
            const current = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={current ? "page" : undefined}
                className={`${ROW} ${
                  current
                    ? "border-hairline bg-canvas font-medium text-ink"
                    : "text-body hover:bg-surface-strong/60 hover:text-ink"
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
            action={
              <Link
                href="/app/archived"
                className="text-[12px] text-muted-soft underline-offset-2 hover:text-ink hover:underline"
              >
                {t("common.archived")}
              </Link>
            }
          >
            {t("common.monitors")}
          </SectionLabel>
          <MonitorList onNavigate={() => setOpen(false)} />
          <SectionLabel
            action={
              <Link
                href="/app/archived-conversations"
                className="text-[12px] text-muted-soft underline-offset-2 hover:text-ink hover:underline"
              >
                {t("common.archived")}
              </Link>
            }
          >
            {t("common.conversations")}
          </SectionLabel>
          <Suspense fallback={null}>
            <ConversationList onNavigate={() => setOpen(false)} />
          </Suspense>
        </div>

        <div className="flex h-16 items-center gap-2 border-t px-3">
          <span
            aria-hidden
            className="grid size-8 shrink-0 place-items-center rounded-full border border-hairline bg-canvas text-[12px] font-medium text-ink"
          >
            {initial}
          </span>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[13px] font-medium text-ink">{user.display_name}</p>
            <p className="truncate text-[12px] text-muted-soft">
              {user.role === "admin" ? t("common.admin") : t("common.member")}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="size-7 text-muted-soft hover:text-ink"
            aria-label={t("common.logout")}
            onClick={() => { setLogoutError(null); void logout().catch(setLogoutError); }}
          >
            <LogOut className="size-4" strokeWidth={1.5} />
          </Button>
        </div>
        {logoutError && <p role="alert" className="px-3 pb-2 text-[13px] text-error">{errorText(logoutError)}</p>}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center gap-3 border-b border-hairline bg-canvas px-4 md:hidden">
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label={t("common.openNavigation")}
            aria-expanded={open}
            aria-controls="workspace-navigation"
            onClick={() => setOpen(true)}
          >
            <Menu className="size-4" strokeWidth={1.5} />
          </Button>
          <span className="flex items-center gap-2.5 font-display text-[20px] leading-none tracking-[-0.02em] text-ink">
            <Radar className="size-[18px] text-primary" strokeWidth={1.5} />
            WebMonitor
          </span>
          <span className="truncate text-[14px] text-muted-soft">
            {section}
          </span>
          <LanguageSwitcher className="ml-auto" />
        </header>
        <main id="workspace-main" tabIndex={-1} className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
