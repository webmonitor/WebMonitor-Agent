"use client";
import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChatPanel } from "@/features/chat/chat-panel";
import { CreateMonitorCard } from "@/features/chat/create-monitor-card";
import { MonitorSummary } from "@/features/monitors/monitor-summary";
import { RecentEvents } from "@/features/events/recent-events";
import { useConversation, useConversations } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/client";
import { useI18n } from "@/lib/i18n";

function ContextPanel({
  conversationId,
  pendingDraftId,
  monitorId,
}: {
  conversationId: string;
  pendingDraftId?: string;
  monitorId?: string;
}) {
  const { t } = useI18n();
  const conversation = useConversation(conversationId);
  const draft = conversation.data?.drafts.find((item) => item.id === pendingDraftId);

  return (
    <aside className="hidden h-full min-h-0 flex-col gap-6 overflow-y-auto border-l bg-card px-4 py-5 xl:flex">
      {draft ? (
        <CreateMonitorCard conversationId={conversationId} draft={draft} />
      ) : monitorId ? (
        <MonitorSummary monitorId={monitorId} />
      ) : (
        <section className="surface-pad space-y-1.5">
          <h2 className="text-[14px] font-medium">{t("chat.context.emptyTitle")}</h2>
          <p className="meta">{t("chat.context.emptyBody")}</p>
        </section>
      )}
      {monitorId && <RecentEvents monitorId={monitorId} />}
    </aside>
  );
}

function WorkspaceView() {
  const params = useSearchParams();
  const router = useRouter();
  const conversationId = params.get("conversation");
  const conversations = useConversations();
  const conversation = useConversation(conversationId);

  const items = conversations.data?.items ?? [];
  const first = items[0];
  // A link to a conversation that no longer exists opens a fresh draft instead
  // of an error: reloading the same address can never make it exist again.
  const missing =
    Boolean(conversationId) &&
    conversation.error instanceof ApiError &&
    conversation.error.status === 404;
  const activeId = missing ? null : conversationId;
  // `new=1` opens an unsaved draft; an empty account starts in it directly.
  const drafting =
    !activeId && (missing || params.get("new") === "1" || (conversations.isSuccess && items.length === 0));

  useEffect(() => {
    if (missing) router.replace("/app?new=1");
  }, [missing, router]);

  useEffect(() => {
    if (!activeId && !drafting && first) {
      router.replace(`/app?conversation=${first.id}`);
    }
  }, [activeId, drafting, first, router]);

  const drafts = conversation.data?.drafts ?? [];
  const pending = drafts.filter((draft) => draft.status === "draft").at(-1);
  const monitorId = drafts.filter((draft) => draft.monitor_id).at(-1)?.monitor_id ?? undefined;

  return (
    <div
      className={`grid h-full min-h-0 grid-cols-1 grid-rows-[minmax(0,1fr)] ${
        activeId ? "xl:grid-cols-[minmax(0,1fr)_21rem]" : ""
      }`}
    >
      <ChatPanel conversationId={activeId} drafting={drafting} pendingDraft={pending} />
      {activeId && (
        <ContextPanel
          conversationId={activeId}
          pendingDraftId={pending?.id}
          monitorId={monitorId}
        />
      )}
    </div>
  );
}

export default function WorkspacePage() {
  const { t } = useI18n();
  return (
    <Suspense fallback={<p className="meta p-6">{t("chat.workspace.loading")}</p>}>
      <WorkspaceView />
    </Suspense>
  );
}
