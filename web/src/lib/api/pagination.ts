export type Page<T> = { items: T[]; total: number };

const OVERLAP = 20;
const MULTI_PAGE_MIN_INTERVAL = 60_000;

/**
 * Re-read a small overlap because rows can shift while later pages are loaded.
 * There is deliberately no page ceiling: every row remains reachable and cached.
 */
export function nextPageOffset<T extends { id: string }>(
  pages: Page<T>[],
  lastParam: number,
  limit: number,
): number | undefined {
  const last = pages.at(-1);
  if (!last || last.items.length === 0) return undefined;
  const loaded = pages.reduce((count, page) => count + page.items.length, 0);
  const unique = new Set(pages.flatMap((page) => page.items.map((row) => row.id))).size;
  if (unique >= last.total) return undefined;
  // Never overlap a whole page away: small limits must still move forward.
  const overlap = Math.min(OVERLAP, Math.floor(limit / 2));
  const next = Math.max(0, loaded - overlap);
  return next > lastParam ? next : undefined;
}

/** Last-write-wins by id without discarding pages already shown to the reader. */
export function mergePages<T extends { id: string }>(pages: Page<T>[]): Page<T> {
  return {
    items: [...new Map(pages.flatMap((page) => page.items).map((row) => [row.id, row])).values()],
    total: pages[0]?.total ?? 0,
  };
}

/** Multi-page lists still recover from remote changes, but poll less often. */
export function pageRefetchInterval(pageCount: number, interval: number): number {
  return pageCount > 1 ? Math.max(interval, MULTI_PAGE_MIN_INTERVAL) : interval;
}
