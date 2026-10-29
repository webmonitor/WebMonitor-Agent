"use client";
import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChatPanel } from "@/features/chat/chat-panel";
import { DraftCard } from "@/features/chat/draft-card";
import { MonitorRail } from "@/features/monitors/monitor-rail";
import { useConversation, useConversations } from "@/lib/api/hooks";

function WorkspaceView() {
  const params = useSearchParams();
  const router = useRouter();
  const conversationId = params.get("conversation");
  const conversations = useConversations();
  const conversation = useConversation(conversationId);
  const latestDraft = conversation.data?.drafts.at(-1) ?? null;

  const first = conversations.data?.items[0];
  useEffect(() => {
    if (!conversationId && first) {
      router.replace(`/app?conversation=${first.id}`);
    }
  }, [conversationId, first, router]);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <ChatPanel conversationId={conversationId} />
      <aside className="hidden min-h-0 flex-col gap-4 overflow-y-auto border-l bg-muted/20 px-4 py-4 lg:flex">
        {conversationId && latestDraft && (
          <DraftCard conversationId={conversationId} draft={latestDraft} />
        )}
        <MonitorRail activeId={latestDraft?.monitor_id ?? undefined} />
      </aside>
    </div>
  );
}

export default function WorkspacePage() {
  return (
    <Suspense
      fallback={<p className="p-6 text-sm text-muted-foreground">正在打开工作台…</p>}
    >
      <WorkspaceView />
    </Suspense>
  );
}
