import type { MessageKey } from "@/lib/i18n/messages";

/** Keep concrete records ahead of their parent sections. */
export function titleKey(pathname: string): MessageKey | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (path === "/") return "common.siteTitle";
  if (path === "/login" || path.startsWith("/login/")) return "common.title.login";
  if (path === "/register" || path.startsWith("/register/")) return "common.title.register";
  if (/^\/app\/monitors\/[^/]+\/snapshots\/[^/]+$/.test(path)) return "common.title.snapshot";
  if (path === "/app/monitors") return "common.title.monitors";
  if (path.startsWith("/app/monitors/")) return "common.title.monitor";
  if (path === "/app/archived-conversations" || path.startsWith("/app/archived-conversations/")) {
    return "chat.archive.title";
  }
  if (path === "/app/archived" || path.startsWith("/app/archived/")) return "common.title.archived";
  if (path === "/app/events" || path.startsWith("/app/events/")) return "common.title.events";
  if (path === "/app/notifications" || path.startsWith("/app/notifications/")) {
    return "common.title.notifications";
  }
  if (path === "/app/templates" || path.startsWith("/app/templates/")) return "common.title.templates";
  if (path === "/app/tokens" || path.startsWith("/app/tokens/")) return "common.title.tokens";
  if (path === "/app/members" || path.startsWith("/app/members/")) return "common.title.members";
  if (path === "/app/system" || path.startsWith("/app/system/")) return "system.title";
  if (path === "/app" || path.startsWith("/app/")) return "common.title.workspace";
  return null;
}
