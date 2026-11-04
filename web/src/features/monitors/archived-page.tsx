"use client";
import Link from "next/link";
import { RotateCcw } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { ListPagination } from "@/components/list-pagination";
import { PageBody, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { useMonitors, useRestoreMonitor } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

/** Archived monitors keep their definition and history; they only stop running. */
export function ArchivedPage() {
  const { t } = useI18n();
  const { errorText, formatDateTime } = useFormat();
  const monitors = useMonitors(true);
  const restore = useRestoreMonitor();
  const items = monitors.data?.items ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title={t("archived.title")}
          description={t("archived.description")}
        />
        {monitors.isPending && <p className="meta">{t("common.loading")}</p>}
        {monitors.error && <p role="alert" className="text-sm text-error">{t("common.listError")}</p>}
        {restore.error && <p role="alert" className="text-sm text-error">{errorText(restore.error)}</p>}
        {!monitors.isPending && !monitors.error && items.length === 0 && (
          <EmptyState
            title={t("archived.emptyTitle")}
            description={t("archived.emptyBody")}
          />
        )}
        <ul className="border-t">
          {items.map((monitor) => (
            <li key={monitor.id} className="flex flex-wrap items-center gap-3 border-b border-hairline py-4">
              <Link
                href={`/app/monitors/${monitor.id}`}
                className="min-w-0 flex-1 truncate text-[14px] font-medium text-ink underline-offset-2 hover:underline"
              >
                {monitor.name}
              </Link>
              <span className="num text-[12px] text-muted-soft">
                {monitor.archived_at ? formatDateTime(monitor.archived_at) : "—"}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={restore.isPending}
                onClick={() => restore.mutate(monitor.id)}
              >
                <RotateCcw strokeWidth={1.5} />
                {t("monitors.action.restore")}
              </Button>
            </li>
          ))}
        </ul>
        <ListPagination query={monitors} />
      </PageBody>
    </div>
  );
}
