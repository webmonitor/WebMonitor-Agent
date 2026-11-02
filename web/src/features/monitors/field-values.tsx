"use client";
import { Fragment } from "react";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

function ItemValue({ item, labels }: { item: unknown; labels: Record<string, string> }) {
  const { formatValue } = useFormat();
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return <span className="num break-words">{formatValue(item)}</span>;
  }
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-0.5">
      {Object.entries(item as Record<string, unknown>).map(([key, value]) => (
        <Fragment key={key}>
          <dt className="text-[11px] text-muted-foreground">{labels[key] ?? key}</dt>
          <dd className="num break-words">{formatValue(value)}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

/**
 * Extracted values as a ledger. A list is never flattened into one line: each
 * row keeps its own field names so added, removed and updated entries read as
 * records rather than as a string.
 */
export function FieldValues({
  values,
  labels,
  mode = "full",
  emptyLabel,
}: {
  values: Record<string, unknown>;
  labels: Record<string, string>;
  mode?: "compact" | "full";
  emptyLabel?: string;
}) {
  const { t } = useI18n();
  const { formatValue } = useFormat();
  const entries = Object.entries(values);
  if (entries.length === 0) return <p className="meta">{emptyLabel ?? t("monitors.content.noFields")}</p>;
  return (
    <dl className="divide-y">
      {entries.map(([name, value]) => (
        <div key={name} className="py-2">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="min-w-0 text-[12px] text-muted-foreground">{labels[name] ?? name}</dt>
            {!Array.isArray(value) && (
              <dd className="num min-w-0 max-w-[65%] text-right text-[13px] break-words">
                {formatValue(value)}
              </dd>
            )}
            {Array.isArray(value) && mode === "compact" && (
              <dd className="num shrink-0 text-[12px] text-muted-foreground">
                {t("monitors.content.itemsCount", { count: value.length })}
              </dd>
            )}
          </div>
          {Array.isArray(value) && mode === "full" && (
            <dd className="mt-1.5">
              {value.length === 0 ? (
                <p className="meta">{t("monitors.content.itemsCount", { count: 0 })}</p>
              ) : (
                <ul className="space-y-1">
                  {value.map((item, index) => (
                    <li
                      key={index}
                      className="rounded-md border bg-muted/20 px-2 py-1.5 text-[12px]"
                    >
                      <ItemValue item={item} labels={labels} />
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          )}
        </div>
      ))}
    </dl>
  );
}
