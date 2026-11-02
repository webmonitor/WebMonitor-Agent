"use client";

import Link from "next/link";
import { RotateCcw } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { ListPagination } from "@/components/list-pagination";
import { PageBody, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { useConversations, useRestoreConversation } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

/** Archived conversations keep their messages; they only leave the sidebar. */
export function ArchivedConversationsPage() {
  const { t } = useI18n();
  const { errorText, formatDateTime } = useFormat();
  const conversations = useConversations(true);
  const restore = useRestoreConversation();
  const items = conversations.data?.items ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title={t("chat.archive.title")}
          description={t("chat.archive.description")}
        />
        {conversations.isPending && <p className="meta">{t("common.loading")}</p>}
        {conversations.error && (
          <p role="alert" className="text-sm text-error">{t("common.listError")}</p>
        )}
        {restore.error && (
          <p role="alert" className="text-sm text-error">{errorText(restore.error)}</p>
        )}
        {!conversations.isPending && !conversations.error && items.length === 0 && (
          <EmptyState
            title={t("chat.archive.emptyTitle")}
            description={t("chat.archive.emptyBody")}
          />
        )}
        <ul className="border-t">
          {items.map((conversation) => (
            <li key={conversation.id} className="flex flex-wrap items-center gap-3 border-b py-3">
              <Link
                href={`/app?conversation=${conversation.id}`}
                className="min-w-0 flex-1 truncate text-[13px] font-medium underline-offset-2 hover:underline"
              >
                {conversation.title?.trim() || t("common.untitledConversation")}
              </Link>
              <span className="num text-[11px] text-muted-foreground">
                {formatDateTime(conversation.updated_at)}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={restore.isPending}
                onClick={() => restore.mutate(conversation.id)}
              >
                <RotateCcw strokeWidth={1.5} />
                {t("chat.archive.restore")}
              </Button>
            </li>
          ))}
        </ul>
        <ListPagination query={conversations} />
      </PageBody>
    </div>
  );
}
