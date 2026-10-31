"use client";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

type PagedList = {
  data?: { items: unknown[]; total: number };
  error: unknown;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => Promise<unknown>;
  refetch: () => Promise<unknown>;
};

export function ListPagination({ query }: { query: PagedList }) {
  const { t } = useI18n();
  return (
    <div className="space-y-2 py-2 text-xs text-muted-foreground">
      {Boolean(query.error) && (
        <div role="alert" className="space-y-1 text-error">
          <p>{t("common.listError")}</p>
          <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      )}
      {query.data && query.data.total > 0 && (
        <p>{t("common.loadedCount", { count: query.data.items.length, total: query.data.total })}</p>
      )}
      {query.hasNextPage && (
        <Button size="sm" variant="outline" disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}>
          {query.isFetchingNextPage ? t("common.loading") : t("common.loadMore")}
        </Button>
      )}
    </div>
  );
}
