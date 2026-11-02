"use client";
import { useState } from "react";
import { Check, Copy, Pencil } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ListPagination } from "@/components/list-pagination";
import { useGroups, useSpecVersions, type MonitorDetail } from "@/lib/api/hooks";
import { parseSpec, type BrowserStep, type SpecField } from "@/lib/api/preview";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

function normalizationEntries(normalize?: SpecField["normalize"]): string[] {
  if (!normalize) return [];
  const entries: string[] = [];
  const push = (key: string, value: unknown) => {
    if (value === null || value === undefined || value === "" || value === false) return;
    if (Array.isArray(value) && value.length === 0) return;
    entries.push(`${key}=${Array.isArray(value) ? value.join("|") : String(value)}`);
  };
  push("trim", normalize.trim);
  push("collapse_whitespace", normalize.collapse_whitespace);
  push("decimal_separator", normalize.decimal_separator);
  push("thousands_separator", normalize.thousands_separator);
  push("currency", normalize.currency);
  push("date_format", normalize.date_format);
  push("timezone", normalize.timezone);
  push("true_values", normalize.true_values);
  push("false_values", normalize.false_values);
  return entries;
}

function FieldRow({ field, labels }: { field: SpecField; labels: Record<string, string> }) {
  const { t } = useI18n();
  const normalize = normalizationEntries(field.normalize);
  const selector = field.selector
    ? `${field.selector}${field.attribute ? ` [${field.attribute}]` : ""}`
    : "—";
  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="min-w-0 text-[13px] font-medium">
          {labels[field.name] ?? field.name}
          <span className="num ml-2 text-[11px] font-normal text-muted-foreground">{field.name}</span>
        </span>
        <span className="num text-[11px] text-muted-foreground">
          {field.type}
          {" · "}
          {field.required === false ? t("monitors.config.optional") : t("monitors.config.required")}
        </span>
      </div>
      <p className="num mt-1 break-all text-[12px] text-muted-foreground">{selector}</p>
      {normalize.length > 0 && (
        <p className="num mt-1 break-all text-[11px] text-muted-foreground">
          {t("monitors.config.normalize")} · {normalize.join(" · ")}
        </p>
      )}
      {field.item_fields && field.item_fields.length > 0 && (
        <ul className="mt-1.5 space-y-1 border-l pl-3">
          {field.item_fields.map((item) => (
            <li key={item.name} className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="text-[12px]">
                {labels[item.name] ?? item.semantic ?? item.name}
                <span className="num ml-2 text-[11px] text-muted-foreground">{item.name}</span>
              </span>
              <span className="num break-all text-[11px] text-muted-foreground">
                {item.selector ?? item.name}
                {item.attribute ? ` [${item.attribute}]` : ""}
                {item.required === false ? ` · ${t("monitors.config.optional")}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function stepText(
  step: BrowserStep,
  labels: { wait: string; scroll: string; next: string },
): string {
  switch (step.type) {
    case "wait_for_selector":
      return [labels.wait, step.selector, `${step.timeout_ms ?? 0}ms`].filter(Boolean).join(" · ");
    case "scroll":
      return [labels.scroll, String(step.max_steps ?? 0)].join(" · ");
    case "click_next":
      return [labels.next, step.selector, String(step.max_pages ?? 0)].filter(Boolean).join(" · ");
    default:
      return step.type;
  }
}

/**
 * The monitor's actual definition, not a summary of it: selectors, per-field
 * normalization, rules, schedule and the raw spec the worker executes.
 */
export function MonitorConfig({
  monitor,
  onEdit,
  onRestore,
}: {
  monitor: MonitorDetail;
  onEdit: () => void;
  onRestore: (spec: unknown) => void;
}) {
  const { t } = useI18n();
  const {
    coverageLabel,
    describeRule,
    fieldLabels,
    formatDateTime,
    formatInterval,
    formatMode,
    formatTimezone,
  } = useFormat();
  const groups = useGroups();
  const versions = useSpecVersions(monitor.id);
  const spec = parseSpec(monitor.spec);
  const [copied, setCopied] = useState(false);
  const [openVersion, setOpenVersion] = useState<string | null>(null);
  const raw = JSON.stringify(monitor.spec, null, 2);

  async function copy() {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  const labels = spec ? fieldLabels(spec.fields) : {};
  const editable = !monitor.archived_at;
  const groupNames = new Map((groups.data?.items ?? []).map((group) => [group.id, group.name]));
  const groupLabels = (spec?.notification_group_ids ?? []).map(
    (id) => groupNames.get(id) ?? (groups.isPending ? "…" : id),
  );
  const coverage = spec?.coverage;

  return (
    <section className="surface mb-8">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 className="section-title">{t("monitors.config.title")}</h2>
          <p className="meta mt-1 max-w-xl leading-5">{t("monitors.config.description")}</p>
        </div>
        {editable && (
          <Button variant="outline" size="sm" onClick={onEdit}>
            <Pencil strokeWidth={1.5} />
            {t("monitors.config.edit")}
          </Button>
        )}
      </header>

      <dl className="grid border-b sm:grid-cols-2 lg:grid-cols-4 lg:divide-x">
        <div className="border-b px-4 py-3 lg:border-b-0">
          <dt className="label-line">{t("monitors.config.schedule")}</dt>
          <dd className="num mt-1 text-[13px]">
            {spec?.schedule
              ? `${formatInterval(spec.schedule.interval_seconds)} · ${formatTimezone(spec.schedule.timezone)}`
              : "—"}
          </dd>
        </div>
        <div className="border-b px-4 py-3 lg:border-b-0">
          <dt className="label-line">{t("monitors.config.collection")}</dt>
          <dd className="mt-1 text-[13px]">{formatMode(monitor.collection_mode)}</dd>
        </div>
        <div className="border-b px-4 py-3 lg:border-b-0">
          <dt className="label-line">{t("monitors.config.coverage")}</dt>
          <dd className="mt-1 text-[13px]">
            {coverageLabel(coverage?.scope)}
            {coverage?.description && (
              <span className="meta mt-0.5 block break-words">{coverage.description}</span>
            )}
          </dd>
        </div>
        <div className="px-4 py-3">
          <dt className="label-line">{t("monitors.config.version")}</dt>
          <dd className="num mt-1 text-[13px]">
            {t("monitors.config.versionValue", { version: monitor.spec_version })}
          </dd>
        </div>
      </dl>

      <div className="grid gap-8 px-4 py-4 lg:grid-cols-2">
        <div>
          <h3 className="label-line">{t("monitors.config.fields")}</h3>
          {!spec || spec.fields.length === 0 ? (
            <p className="meta mt-1.5">{t("monitors.content.noFields")}</p>
          ) : (
            <ul className="mt-1.5 divide-y border-t">
              {spec.fields.map((field) => (
                <FieldRow key={field.name} field={field} labels={labels} />
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-5">
          <div>
            <h3 className="label-line">{t("monitors.config.rules")}</h3>
            <p className="meta mt-1">
              {spec?.change_rules?.mode === "all"
                ? t("monitors.config.ruleModeAll")
                : t("monitors.config.ruleModeAny")}
            </p>
            <ul className="mt-1.5 divide-y border-t">
              {(spec?.change_rules?.rules ?? []).map((rule, index) => (
                <li key={`${rule.type ?? "rule"}-${index}`} className="flex gap-3 py-1.5 text-[13px]">
                  <span className="num mt-0.5 w-4 shrink-0 text-[11px] text-muted-foreground">
                    {index + 1}
                  </span>
                  <span className="min-w-0">{describeRule(rule, labels)}</span>
                </li>
              ))}
            </ul>
          </div>

          {spec?.business_key && (
            <div>
              <h3 className="label-line">{t("monitors.config.businessKey")}</h3>
              <p className="num mt-1 text-[13px]">
                {labels[spec.business_key.field] ?? spec.business_key.field}
                {" · "}
                {spec.business_key.item_fields.join(" + ")}
              </p>
            </div>
          )}

          <div>
            <h3 className="label-line">{t("monitors.config.notifications")}</h3>
            {groupLabels.length === 0 ? (
              <p className="meta mt-1">{t("monitors.config.noGroups")}</p>
            ) : (
              <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                {groupLabels.map((label) => (
                  <li key={label} className="text-[13px]">{label}</li>
                ))}
              </ul>
            )}
            {(monitor.approved_recipients ?? []).length > 0 && (
              <p className="meta mt-1.5 break-words">
                {t("monitors.config.recipients")} · {(monitor.approved_recipients ?? []).join(" · ")}
              </p>
            )}
          </div>

          <div>
            <h3 className="label-line">{t("monitors.config.browserSteps")}</h3>
            {(spec?.browser_steps ?? []).length === 0 ? (
              <p className="meta mt-1">{t("monitors.config.noBrowserSteps")}</p>
            ) : (
              <ul className="mt-1.5 divide-y border-t">
                {(spec?.browser_steps ?? []).map((step, index) => (
                  <li key={`${step.type}-${index}`} className="num break-all py-1.5 text-[12px]">
                    {stepText(step, {
                      wait: t("monitors.step.waitForSelector"),
                      scroll: t("monitors.step.scroll"),
                      next: t("monitors.step.clickNext"),
                    })}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      <details className="border-t px-4 py-3">
        <summary className="cursor-pointer list-none text-[12px] text-muted-foreground transition-colors duration-150 select-none hover:text-foreground">
          {t("monitors.config.versions")}
        </summary>
        {versions.isPending && <p className="meta mt-2">{t("monitors.loadingShort")}</p>}
        {versions.error && <p className="meta mt-2">{t("common.listError")}</p>}
        <ul className="mt-2 divide-y border-t">
          {(versions.data?.items ?? []).map((version) => (
            <li key={version.draft_id} className="space-y-1.5 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex flex-wrap items-center gap-2 text-[12px]">
                  {t("monitors.config.versionValue", { version: version.version })}
                  {version.current && (
                    <Badge tone="success">{t("monitors.config.versionCurrent")}</Badge>
                  )}
                  <span className="num text-[11px] text-muted-foreground">
                    {formatDateTime(version.published_at)}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                    onClick={() => setOpenVersion(openVersion === version.draft_id ? null : version.draft_id)}
                  >
                    {openVersion === version.draft_id
                      ? t("monitors.config.versionHide")
                      : t("monitors.config.versionView")}
                  </button>
                  {!version.current && editable && (
                    <button
                      type="button"
                      className="text-[11px] text-primary underline-offset-2 hover:underline"
                      onClick={() => onRestore(version.spec)}
                    >
                      {t("monitors.config.versionRestore")}
                    </button>
                  )}
                </span>
              </div>
              {openVersion === version.draft_id && (
                <pre className="max-h-64 overflow-auto rounded-lg border bg-muted/40 p-2 text-[11px] leading-relaxed">
                  {JSON.stringify(version.spec, null, 2)}
                </pre>
              )}
            </li>
          ))}
        </ul>
        <ListPagination query={versions} />
      </details>

      <details className="border-t px-4 py-3">
        <summary className="cursor-pointer list-none text-[12px] text-muted-foreground transition-colors duration-150 select-none hover:text-foreground">
          {t("monitors.config.raw")}
        </summary>
        <pre className="mt-2 max-h-80 overflow-auto rounded-lg border bg-muted/40 p-3 text-[11px] leading-relaxed">
          {raw}
        </pre>
        <Button variant="ghost" size="sm" className="mt-2 h-7 px-2 text-xs text-muted-foreground" onClick={() => void copy()}>
          {copied ? <Check strokeWidth={1.5} /> : <Copy strokeWidth={1.5} />}
          {copied ? t("monitors.config.copied") : t("monitors.config.copy")}
        </Button>
      </details>
    </section>
  );
}
