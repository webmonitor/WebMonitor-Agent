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
 * A record's own name, not its bookkeeping. The monitor's business key says
 * which item fields identify a row; without one, the first plain text value does.
 */
function primaryIndex(
  entries: [string, unknown][],
  businessKey: readonly string[],
): number {
  const byKey = entries.findIndex(([key]) => businessKey.includes(key));
  if (byKey >= 0) return byKey;
  return entries.findIndex(
    ([, value]) => typeof value === "string" && !isHttpUrl(value) && !isIsoDate(value),
  );
}

/**
 * Each field's declared type, keyed by name. The type decides how a value is
 * written — a date field shows a date, everything else keeps its full time.
 */
export function fieldTypes(
  fields: { name: string; type?: string; item_fields?: unknown }[],
): Record<string, string> {
  const types: Record<string, string> = {};
  const collect = (items: { name: string; type?: string; item_fields?: unknown }[]) => {
    for (const field of items) {
      if (field.type) types[field.name] ??= field.type;
      if (Array.isArray(field.item_fields)) {
        collect(field.item_fields as { name: string; type?: string; item_fields?: unknown }[]);
      }
    }
  };
  collect(fields);
  return types;
}

/**
 * One row of a list: the entry's name on its own line, then the facts that
 * identify it. Dates and links are unambiguous, so they carry no label; every
 * other field keeps its name.
 */
function RecordRow({
  item,
  labels,
  types,
  businessKey,
}: {
  item: unknown;
  labels: Record<string, string>;
  types?: Record<string, string>;
  businessKey: readonly string[];
}) {
  const { formatValue } = useFormat();
  if (item === null || typeof item !== "object" || Array.isArray(item)) {
    return <span className="num text-[13px] break-words">{formatValue(item)}</span>;
  }
  const entries = Object.entries(item as Record<string, unknown>);
  const primary = primaryIndex(entries, businessKey);
  const title = primary >= 0 ? entries[primary] : undefined;
  const rest = entries.filter((_, index) => index !== primary);
  return (
    <div className="min-w-0 space-y-0.5">
      {title && (
        <p className="text-[13px] leading-5 break-words">{formatValue(title[1], types?.[title[0]])}</p>
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
                <span className="num">{formatValue(value, types?.[key])}</span>
              ) : (
                <>
                  <span>{labels[key] ?? key}</span>
                  <span className="num text-foreground">{formatValue(value, types?.[key])}</span>
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
  types,
  businessKey = [],
  mode = "full",
  emptyLabel,
  maxItems,
}: {
  values: Record<string, unknown>;
  labels: Record<string, string>;
  /** Declared field types, from `fieldTypes`; only `date` changes the rendering. */
  types?: Record<string, string>;
  /** Item fields that name a row; the monitor's business key. */
  businessKey?: readonly string[];
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
                  {formatValue(value, types?.[name])}
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
                        <RecordRow item={item} labels={labels} types={types} businessKey={businessKey} />
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
