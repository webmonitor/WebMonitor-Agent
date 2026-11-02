"use client";
import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

function isHttpUrl(value: unknown): value is string {
  return typeof value === "string" && /^https?:\/\//.test(value);
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value);
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/**
 * A record's own name, not its bookkeeping: prefer a title-like key, then the
 * first value that is plainly text rather than a date or a URL.
 */
function primaryIndex(
  entries: [string, unknown][],
  labels: Record<string, string>,
): number {
  const byName = entries.findIndex(
    ([key]) => /^(title|name|label|headline|subject)$/i.test(key) || /标题|名称/.test(labels[key] ?? ""),
  );
  if (byName >= 0) return byName;
  return entries.findIndex(
    ([, value]) => typeof value === "string" && !isHttpUrl(value) && !isIsoDate(value),
  );
}

/**
 * One row of a list: the entry's name on its own line, then the facts that
 * identify it. Dates and links are unambiguous, so they carry no label; every
 * other field keeps its name.
 */
function RecordRow({
  item,
  labels,
}: {
  item: unknown;
  labels: Record<string, string>;
}) {
  const { formatValue } = useFormat();
  if (item === null || typeof item !== "object" || Array.isArray(item)) {
    return <span className="num text-[13px] break-words">{formatValue(item)}</span>;
  }
  const entries = Object.entries(item as Record<string, unknown>);
  const primary = primaryIndex(entries, labels);
  const title = primary >= 0 ? entries[primary] : undefined;
  const rest = entries.filter((_, index) => index !== primary);
  return (
    <div className="min-w-0 space-y-0.5">
      {title && (
        <p className="text-[13px] leading-5 break-words">{formatValue(title[1])}</p>
      )}
      {rest.length > 0 && (
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[11px] leading-4 text-muted-foreground">
          {rest.map(([key, value]) => (
            <span key={key} className="inline-flex min-w-0 items-baseline gap-1">
              {isHttpUrl(value) ? (
                <a
                  className="inline-flex min-w-0 items-center gap-1 text-primary underline-offset-2 hover:underline"
                  href={value}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="num truncate">{hostOf(value)}</span>
                  <ExternalLink className="size-3 shrink-0" strokeWidth={1.5} />
                </a>
              ) : isIsoDate(value) ? (
                <span className="num">{formatValue(value)}</span>
              ) : (
                <>
                  <span>{labels[key] ?? key}</span>
                  <span className="num text-foreground">{formatValue(value)}</span>
                </>
              )}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

/**
 * Extracted values as a ledger. A list is never flattened into one line: each
 * row keeps its own name and identifying facts so added, removed and updated
 * entries read as records rather than as a string.
 */
export function FieldValues({
  values,
  labels,
  mode = "full",
  emptyLabel,
  maxItems,
}: {
  values: Record<string, unknown>;
  labels: Record<string, string>;
  mode?: "compact" | "full";
  emptyLabel?: string;
  maxItems?: number;
}) {
  const { t } = useI18n();
  const { formatValue } = useFormat();
  const [expanded, setExpanded] = useState(false);
  const entries = Object.entries(values);
  if (entries.length === 0) return <p className="meta">{emptyLabel ?? t("monitors.content.noFields")}</p>;

  return (
    <dl className="divide-y">
      {entries.map(([name, value]) => {
        const items = Array.isArray(value) ? value : null;
        const limit = mode === "full" ? (maxItems ?? items?.length ?? 0) : (maxItems ?? 3);
        const shown = items ? (mode === "full" && expanded ? items : items.slice(0, limit)) : [];
        return (
          <div key={name} className="py-2">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="min-w-0 text-[12px] text-muted-foreground">{labels[name] ?? name}</dt>
              {items ? (
                <dd className="num shrink-0 text-[11px] text-muted-foreground">
                  {t("monitors.content.itemsCount", { count: items.length })}
                </dd>
              ) : (
                <dd className="num min-w-0 max-w-[65%] text-right text-[13px] break-words">
                  {formatValue(value)}
                </dd>
              )}
            </div>
            {items && (
              <dd className="mt-1.5">
                {items.length === 0 ? (
                  <p className="meta">{t("monitors.content.itemsCount", { count: 0 })}</p>
                ) : (
                  <ul className={mode === "full" ? "divide-y border-t" : "space-y-1.5"}>
                    {shown.map((item, index) => (
                      <li key={index} className={mode === "full" ? "py-1.5 text-[12px]" : "text-[12px]"}>
                        <RecordRow item={item} labels={labels} />
                      </li>
                    ))}
                  </ul>
                )}
                {items.length > shown.length && mode === "full" && (
                  <button
                    type="button"
                    className="mt-1.5 text-[11px] text-muted-foreground underline-offset-2 transition-colors duration-150 hover:text-foreground hover:underline"
                    onClick={() => setExpanded((open) => !open)}
                  >
                    {expanded
                      ? t("monitors.content.collapse")
                      : t("monitors.content.showAll", { count: items.length })}
                  </button>
                )}
                {items.length > shown.length && mode === "compact" && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {t("monitors.content.moreItems", { count: items.length - shown.length })}
                  </p>
                )}
              </dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}
