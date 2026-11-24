"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageBody, PageHeader } from "@/components/page-header";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/messages";
import { useAuth } from "@/lib/providers";

type SystemMetrics = components["schemas"]["SystemMetrics"];
const KIND_LABELS: Record<string, MessageKey> = {
  agent: "system.kind.agent",
  analyze: "system.kind.analyze",
  preview: "system.kind.preview",
  production: "system.kind.production",
};
const MODE_LABELS: Record<string, MessageKey> = {
  http: "system.mode.http",
  browser: "system.mode.browser",
};

export function SystemPage() {
  const { t, locale } = useI18n();
  const { formatDateTime } = useFormat();
  const { user } = useAuth();
  const [hours, setHours] = useState(24);
  const metrics = useQuery({
    queryKey: ["system-metrics", hours],
    queryFn: () => api<SystemMetrics>(`/admin/metrics?hours=${hours}`),
    enabled: user?.role === "admin",
    refetchInterval: 30000,
  });
  const number = new Intl.NumberFormat(locale);
  const percent = (value: number | null) => value === null ? "—" : `${(value * 100).toFixed(1)}%`;
  const duration = (value: number | null) => value === null ? "—" : `${(value / 1000).toFixed(2)} s`;

  if (user && user.role !== "admin") {
    return <div className="grid h-full place-items-center px-6 text-center">
      <p className="text-sm text-muted-foreground">{t("activity.members.adminOnlyBody")}</p>
    </div>;
  }

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader title={t("system.title")} description={t("system.description")} />
        <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
          <label className="space-y-1.5 text-[13px] font-medium text-ink">
            <span className="block">{t("system.window")}</span>
            <select
              className="flex h-9 rounded-md border border-input bg-canvas px-3 text-sm"
              value={hours}
              onChange={(event) => setHours(Number(event.target.value))}
            >
              <option value={24}>{t("system.hours24")}</option>
              <option value={168}>{t("system.hours168")}</option>
              <option value={720}>{t("system.hours720")}</option>
            </select>
          </label>
          <div className="flex items-center gap-3">
            {metrics.data && <span className="meta">{t("system.generated", { date: formatDateTime(metrics.data.generated_at) })}</span>}
            <Button variant="outline" size="sm" disabled={metrics.isFetching} onClick={() => void metrics.refetch()}>
              <RefreshCw strokeWidth={1.5} />
              {t("system.retry")}
            </Button>
          </div>
        </div>
        {metrics.isPending && <p className="meta">{t("common.loading")}</p>}
        {metrics.error && <p role="alert" className="text-sm text-error">{t("system.loadError")}</p>}
        {metrics.data && (
          <div className="space-y-10">
            <section>
              <h2 className="section-title mb-3">{t("system.queue")}</h2>
              <div className="overflow-x-auto rounded-lg border border-hairline">
                <table className="w-full text-left text-[13px]">
                  <thead className="bg-surface-soft text-muted-soft">
                    <tr><th className="px-4 py-2 font-medium">{t("system.kind")}</th><th className="px-4 py-2 font-medium">{t("system.queued")}</th><th className="px-4 py-2 font-medium">{t("system.running")}</th></tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {metrics.data.queue.map((row) => <tr key={row.kind}>
                      <td className="px-4 py-2.5">{t(KIND_LABELS[row.kind] ?? "system.kind.production")}</td>
                      <td className="num px-4 py-2.5">{number.format(row.queued)}</td>
                      <td className="num px-4 py-2.5">{number.format(row.running)}</td>
                    </tr>)}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="section-title mb-3">{t("system.collection")}</h2>
              <div className="overflow-x-auto rounded-lg border border-hairline">
                <table className="w-full text-left text-[13px]">
                  <thead className="bg-surface-soft text-muted-soft"><tr>
                    <th className="px-4 py-2 font-medium">{t("system.mode")}</th><th className="px-4 py-2 font-medium">{t("system.succeeded")}</th><th className="px-4 py-2 font-medium">{t("system.failed")}</th><th className="px-4 py-2 font-medium">{t("system.successRate")}</th><th className="px-4 py-2 font-medium">{t("system.duration")}</th>
                  </tr></thead>
                  <tbody className="divide-y divide-hairline">
                    {metrics.data.collection.map((row) => <tr key={row.mode}>
                      <td className="px-4 py-2.5">{t(MODE_LABELS[row.mode] ?? "system.mode.http")}</td><td className="num px-4 py-2.5">{number.format(row.succeeded)}</td><td className="num px-4 py-2.5">{number.format(row.failed)}</td><td className="num px-4 py-2.5">{percent(row.success_rate)}</td><td className="num px-4 py-2.5">{duration(row.average_duration_ms)}</td>
                    </tr>)}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="section-title mb-3">{t("system.deliveries")}</h2>
              <dl className="grid gap-px overflow-hidden rounded-lg border border-hairline bg-hairline sm:grid-cols-5">
                {([
                  [t("system.active"), metrics.data.deliveries.active],
                  [t("system.sent"), metrics.data.deliveries.sent],
                  [t("system.failed"), metrics.data.deliveries.failed],
                  [t("system.cancelled"), metrics.data.deliveries.cancelled],
                ] as const).map(([label, value]) => <div key={label} className="bg-canvas px-4 py-3">
                  <dt className="meta">{label}</dt><dd className="num mt-1 text-lg">{number.format(value)}</dd>
                </div>)}
                <div className="bg-canvas px-4 py-3"><dt className="meta">{t("system.failureRate")}</dt><dd className="num mt-1 text-lg">{percent(metrics.data.deliveries.failure_rate)}</dd></div>
              </dl>
            </section>

            <section>
              <h2 className="section-title mb-3">{t("system.usage")}</h2>
              {metrics.data.usage.length === 0 ? <p className="meta">{t("system.emptyUsage")}</p> : (
                <div className="overflow-x-auto rounded-lg border border-hairline">
                  <table className="w-full text-left text-[13px]">
                    <thead className="bg-surface-soft text-muted-soft"><tr>
                      <th className="px-4 py-2 font-medium">{t("system.bucket")}</th><th className="px-4 py-2 font-medium">{t("system.user")}</th><th className="px-4 py-2 font-medium">{t("system.requests")}</th><th className="px-4 py-2 font-medium">{t("system.input")}</th><th className="px-4 py-2 font-medium">{t("system.output")}</th><th className="px-4 py-2 font-medium">{t("system.total")}</th>
                    </tr></thead>
                    <tbody className="divide-y divide-hairline">
                      {metrics.data.usage.map((row) => <tr key={`${row.user_id}-${row.bucket}`}>
                        <td className="num px-4 py-2.5">{formatDateTime(row.bucket)}</td><td className="px-4 py-2.5">{row.email}</td><td className="num px-4 py-2.5">{number.format(row.requests)}</td><td className="num px-4 py-2.5">{number.format(row.input_tokens)}</td><td className="num px-4 py-2.5">{number.format(row.output_tokens)}</td><td className="num px-4 py-2.5">{number.format(row.total_tokens)}</td>
                      </tr>)}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        )}
      </PageBody>
    </div>
  );
}
