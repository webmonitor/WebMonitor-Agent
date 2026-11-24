"use client";

import { useMemo } from "react";
import {
  buildFieldDiffs,
  buildNumericTrends,
  chronologicalSnapshots,
  findPreviousSnapshot,
  type FieldDiff,
  type HistoryField,
  type NumericTrendPoint,
} from "@/features/monitors/history-utils";
import { useSnapshots, type SnapshotRecord } from "@/lib/api/hooks";
import type { MonitorSpecView } from "@/lib/api/preview";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

function TrendChart({
  points,
  label,
}: {
  points: NumericTrendPoint[];
  label: string;
}) {
  const width = 640;
  const height = 112;
  const horizontalPadding = 10;
  const verticalPadding = 14;
  const values = points.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const coordinates = points.map((point, index) => ({
    x: points.length === 1
      ? width / 2
      : horizontalPadding + index * (width - horizontalPadding * 2) / (points.length - 1),
    y: minimum === maximum
      ? height / 2
      : height - verticalPadding
        - (point.value - minimum) * (height - verticalPadding * 2) / (maximum - minimum),
  }));

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-28 w-full text-primary"
      role="img"
      aria-label={label}
    >
      <title>{label}</title>
      <line
        x1={horizontalPadding}
        x2={width - horizontalPadding}
        y1={height - verticalPadding}
        y2={height - verticalPadding}
        className="stroke-hairline"
        strokeWidth="1"
        vectorEffect="non-scaling-stroke"
      />
      {coordinates.length > 1 && (
        <polyline
          points={coordinates.map(({ x, y }) => `${x},${y}`).join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      )}
      {coordinates.map(({ x, y }, index) => (
        <circle
          key={points[index].snapshotId}
          cx={x}
          cy={y}
          r="3.5"
          className="fill-canvas stroke-primary"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </svg>
  );
}

function TextDiff({ diff }: { diff: Extract<FieldDiff, { kind: "text" }> }) {
  return (
    <p className="whitespace-pre-wrap break-words text-[14px] leading-6">
      {diff.parts.map((part, index) => {
        if (part.type === "added") {
          return <ins key={index} className="rounded bg-success/10 text-success-ink no-underline">{part.value}</ins>;
        }
        if (part.type === "removed") {
          return <del key={index} className="rounded bg-error/10 text-error">{part.value}</del>;
        }
        return <span key={index}>{part.value}</span>;
      })}
    </p>
  );
}

function ListDiff({ diff }: { diff: Extract<FieldDiff, { kind: "list" }> }) {
  const { t } = useI18n();
  const { formatValue } = useFormat();
  return (
    <ul className="space-y-1.5">
      {diff.parts.map((part, index) => {
        if (part.type === "equal") return null;
        const added = part.type === "added";
        return (
          <li key={index} className="flex items-baseline gap-2 text-[13px] leading-5">
            <span aria-hidden className={`shrink-0 font-medium ${added ? "text-success-ink" : "text-error"}`}>
              {added ? "+" : "−"}
            </span>
            <span className="sr-only">{t(added ? "history.added" : "history.removed")}</span>
            <span className={`min-w-0 break-words rounded px-1.5 py-0.5 ${
              added ? "bg-success/10 text-success-ink" : "bg-error/10 text-error line-through"
            }`}>
              {formatValue(part.value)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function numericValue(
  point: NumericTrendPoint,
  field: HistoryField,
  formatValue: (value: unknown, type?: string) => string,
): string {
  if (field.type === "money" && field.normalize?.currency) {
    return formatValue({ amount: point.value, currency: field.normalize.currency });
  }
  return formatValue(point.value);
}

/** Reusable stored-history view; only the monitor id and current record are required. */
export function SnapshotHistory({
  monitorId,
  current,
  spec,
}: {
  monitorId: string;
  current: SnapshotRecord;
  spec: MonitorSpecView | null;
}) {
  const { t } = useI18n();
  const { fieldLabels, formatDateTime, formatValue } = useFormat();
  const snapshots = useSnapshots(monitorId);
  const stored = snapshots.data?.items;
  const history = useMemo(() => {
    const byId = new Map((stored ?? []).map((snapshot) => [snapshot.id, snapshot]));
    // The detail response wins if polling has a stale copy of the current row.
    byId.set(current.id, current);
    const chronological = chronologicalSnapshots([...byId.values()]);
    const previous = findPreviousSnapshot(chronological, current.id);
    return {
      previous,
      trends: buildNumericTrends(chronological, spec?.fields ?? []),
      diffs: buildFieldDiffs(
        spec?.fields ?? [],
        current.extracted_data,
        previous?.extracted_data ?? null,
      ),
    };
  }, [stored, current, spec]);

  if (!spec) return null;
  const labels = fieldLabels(spec.fields);
  const hasNumericFields = spec.fields.some((field) => field.type === "number" || field.type === "money");
  const hasDiffFields = spec.fields.some((field) => field.type === "text" || field.type === "list");

  return (
    <section className="mt-8 space-y-6" aria-labelledby="snapshot-history-title">
      <header>
        <h2 id="snapshot-history-title" className="section-title">{t("history.title")}</h2>
        <p className="meta mt-1">{t("history.description")}</p>
      </header>

      {snapshots.isPending && <p className="meta">{t("history.loading")}</p>}
      {snapshots.error && <p role="alert" className="text-[13px] text-error">{t("history.error")}</p>}

      {!snapshots.isPending && !snapshots.error && (
        <>
          {hasNumericFields && (
            <section aria-labelledby="snapshot-history-trends">
              <h3 id="snapshot-history-trends" className="mb-3 text-[14px] font-medium text-ink">
                {t("history.trends")}
              </h3>
              <div className="grid gap-4 xl:grid-cols-2">
                {history.trends.map(({ field, points }) => {
                  const label = labels[field.name] ?? field.name;
                  const latest = points[points.length - 1];
                  return (
                    <article key={field.name} className="min-w-0 rounded-lg border border-hairline bg-canvas p-4">
                      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                        <h4 className="min-w-0 text-[13px] text-muted-foreground">{label}</h4>
                        {latest && (
                          <p className="num text-[15px] font-medium text-ink">
                            {numericValue(latest, field, formatValue)}
                          </p>
                        )}
                      </header>
                      {points.length === 0 ? (
                        <p className="meta mt-4">{t("history.noValues")}</p>
                      ) : (
                        <>
                          <div className="mt-3">
                            <TrendChart points={points} label={t("history.chart", { field: label })} />
                          </div>
                          <footer className="mt-1 flex flex-wrap justify-between gap-x-3 gap-y-1 text-[11px] text-muted-soft">
                            <span className="num">{formatDateTime(points[0].collectedAt)}</span>
                            <span className="num">{t("history.valueCount", { count: points.length })}</span>
                            <span className="num">{formatDateTime(latest.collectedAt)}</span>
                          </footer>
                        </>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          {hasDiffFields && (
            <section aria-labelledby="snapshot-history-changes">
              <h3 id="snapshot-history-changes" className="text-[14px] font-medium text-ink">
                {t("history.changes")}
              </h3>
              <p className="meta mt-1">
                {history.previous
                  ? t("history.comparison", { time: formatDateTime(history.previous.collected_at) })
                  : t("history.noPrior")}
              </p>
              {history.previous && history.diffs.length === 0 && (
                <p className="meta mt-3">{t("history.noChanges")}</p>
              )}
              {history.diffs.length > 0 && (
                <div className="mt-3 space-y-3">
                  {history.diffs.map((diff) => (
                    <article key={diff.field.name} className="rounded-lg border border-hairline bg-canvas px-4 py-3">
                      <h4 className="mb-2 text-[13px] text-muted-foreground">
                        {labels[diff.field.name] ?? diff.field.name}
                      </h4>
                      {diff.kind === "text" ? <TextDiff diff={diff} /> : <ListDiff diff={diff} />}
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </section>
  );
}
