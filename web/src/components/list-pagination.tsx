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

/** Counts are quiet text; the only control is a plain "load more". */
export function ListPagination({ query }: { query: PagedList }) {
  const { t } = useI18n();
  return (
    <div className="space-y-2 py-3 t-caption text-muted-foreground">
      {Boolean(query.error) && (
        <div role="alert" className="space-y-1.5 text-error">
          <p>{t("common.listError")}</p>
          <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      )}
      {query.data && query.hasNextPage && query.data.total > 0 && (
        <p className="num text-[13px]">
          {t("common.loadedCount", { count: query.data.items.length, total: query.data.total })}
        </p>
      )}
      {query.hasNextPage && (
        <Button size="sm" variant="link" className="px-0 text-[13px]"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}>
          {query.isFetchingNextPage ? t("common.loading") : t("common.loadMore")}
        </Button>
      )}
    </div>
  );
}
