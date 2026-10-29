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
    <section className="surface-pad space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Badge tone={row.status === "active" ? "success" : "neutral"}>{statusLabel(row.status)}</Badge>
        <Link
          href={`/app/monitors/${row.id}`}
          className="flex items-center gap-1 text-xs text-primary underline-offset-2 hover:underline"
        >
          {t("monitors.summary.open")}
          <ArrowUpRight className="size-3" />
        </Link>
      </div>
      <div className="space-y-0.5">
        <h2 className="truncate text-[15px] font-semibold">{row.name}</h2>
        <p className="meta truncate">
          {t("monitors.summary.interval", { interval: formatInterval(row.interval_seconds) })}
        </p>
      </div>

      {fields.length > 0 && row.baseline_status === "ready" && (
        <ul className="space-y-1 border-t pt-3">
          {fields.slice(0, 4).map((field) => (
            <li key={field.name} className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="shrink-0 text-muted-foreground">{labels[field.name]}</span>
              <span className="truncate text-right font-medium tabular-nums">
                {formatValue(values[field.name])}
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="meta border-t pt-3">
        {row.baseline_status === "ready"
          ? t("monitors.summary.lastCheck", { time: formatTime(row.last_success_at) })
          : t("monitors.summary.awaiting")}
      </p>
    </section>
  );
}
