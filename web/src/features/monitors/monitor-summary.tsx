"use client";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useMonitor } from "@/lib/api/hooks";
import { parseSpec } from "@/lib/api/preview";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

/** Right-hand context after the monitor exists: the result of the conversation. */
export function MonitorSummary({ monitorId }: { monitorId: string }) {
  const { t } = useI18n();
  const { fieldLabels, formatInterval, formatTime, formatValue, statusLabel } = useFormat();
  const monitor = useMonitor(monitorId);

  if (monitor.isPending) {
    return <div className="surface-pad meta">{t("monitors.loading")}</div>;
  }
  if (!monitor.data) return null;

  const row = monitor.data;
  const spec = parseSpec(row.spec);
  const fields = spec?.fields ?? [];
  const labels = fieldLabels(fields);
  const values = row.baseline?.extracted_data ?? {};

  return (
    <section className="surface">
      <div className="flex items-center justify-between gap-2 border-b px-4 py-2.5">
        <Badge tone={row.status === "active" ? "success" : "neutral"}>{statusLabel(row.status)}</Badge>
        <Link
          href={`/app/monitors/${row.id}`}
          className="flex items-center gap-1 text-[11px] text-primary underline-offset-2 hover:underline"
        >
          {t("monitors.summary.open")}
          <ArrowUpRight className="size-3.5" strokeWidth={1.5} />
        </Link>
      </div>

      <div className="space-y-0.5 px-4 py-3">
        <h2 className="truncate text-[14px] font-medium">{row.name}</h2>
        <p className="num text-[11px] text-muted-foreground">
          {t("monitors.summary.interval", { interval: formatInterval(row.interval_seconds) })}
        </p>
      </div>

      {fields.length > 0 && row.baseline_status === "ready" && (
        <dl className="divide-y border-t px-4">
          {fields.slice(0, 4).map((field) => {
            const value = values[field.name];
            return (
              <div key={field.name} className="flex items-baseline justify-between gap-3 py-2">
                <dt className="shrink-0 text-[12px] text-muted-foreground">{labels[field.name]}</dt>
                <dd className="num min-w-0 truncate text-right text-[13px]">
                  {Array.isArray(value)
                    ? t("monitors.content.itemsCount", { count: value.length })
                    : formatValue(value)}
                </dd>
              </div>
            );
          })}
        </dl>
      )}

      <p className="num border-t px-4 py-2.5 text-[11px] text-muted-foreground">
        {row.baseline_status === "ready"
          ? t("monitors.summary.lastCheck", { time: formatTime(row.last_success_at) })
          : t("monitors.summary.awaiting")}
      </p>
    </section>
  );
}
