"use client";
import { useState } from "react";
import { Check, ChevronRight, Copy, Pencil } from "lucide-react";
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
  const location = field.path
    ? `${t("monitors.config.fieldPath")} · ${field.path}`
    : field.selector
      ? `${field.selector}${field.attribute ? ` [${field.attribute}]` : ""}`
      : "—";
  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="min-w-0 text-[14px] font-medium">
          {labels[field.name] ?? field.name}
          <span className="num ml-2 text-[13px] font-normal text-muted-foreground">{field.name}</span>
        </span>
        <span className="num text-[13px] text-muted-soft">
          {field.type}
          {" · "}
          {field.required === false ? t("monitors.config.optional") : t("monitors.config.required")}
        </span>
      </div>
      <p className="num mt-1 break-all text-[13px] text-muted-foreground">{location}</p>
      {normalize.length > 0 && (
        <p className="num mt-1 break-all text-[13px] text-muted-foreground">
          {t("monitors.config.normalize")} · {normalize.join(" · ")}
        </p>
      )}
      {field.item_fields && field.item_fields.length > 0 && (
        <ul className="mt-1.5 space-y-1 border-l pl-3">
          {field.item_fields.map((item) => (
            <li key={item.name} className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="text-[13px]">
                {labels[item.name] ?? item.semantic ?? item.name}
                <span className="num ml-2 text-[13px] text-muted-foreground">{item.name}</span>
              </span>
              <span className="num break-all text-[13px] text-muted-foreground">
                {item.path ?? item.selector ?? item.name}
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

/** The approved design travels as a frozen snapshot, not a typed schema. */
function templateName(monitor: MonitorDetail): string | null {
  const snapshot = monitor.email_template as { name?: unknown } | null | undefined;
  return typeof snapshot?.name === "string" ? snapshot.name : null;
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
 * normalization, rules, browser steps and the raw collection spec the worker
 * executes. Delivery settings (groups, cadence, template) are read from the
 * monitor's own columns, never from the collection spec.
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
  const groupLabels = (monitor.notification_group_ids ?? []).map(
    (id) => groupNames.get(id) ?? (groups.isPending ? "…" : id),
  );
  const coverage = spec?.coverage;

  return (
    <details className="group surface mb-8">
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 px-5 py-4 select-none [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 items-center gap-2">
          <ChevronRight
            className="size-3.5 shrink-0 text-muted-foreground transition-transform duration-150 group-open:rotate-90"
            strokeWidth={1.5}
          />
          <span className="section-title">{t("monitors.config.title")}</span>
          <span className="meta truncate">
            {formatMode(monitor.collection_mode)}
            {" · "}
            {coverageLabel(coverage?.scope)}
          </span>
        </span>
        {editable && (
          <Button
            variant="outline"
            size="sm"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onEdit();
            }}
          >
            <Pencil strokeWidth={1.5} />
            {t("monitors.config.edit")}
          </Button>
        )}
      </summary>

      {coverage?.description && (
        <p className="meta border-t border-hairline px-5 py-3">{coverage.description}</p>
      )}

      <div className="grid gap-10 border-t border-hairline px-5 py-6 lg:grid-cols-2">
        <div>
          {spec?.source && (
            <div className="mb-5">
              <h3 className="label-line">{t("monitors.config.source")}</h3>
              <p className="mt-1 text-[14px]">
                <span className="text-muted-foreground">{t("monitors.config.channel")} · </span>
                {t("monitors.config.channelJson")}
              </p>
              <p className="label-line mt-3">{t("monitors.config.steps")}</p>
              <ul className="mt-1 divide-y border-t">
                {spec.source.steps.map((step) => (
                  <li key={step.id} className="py-1.5">
                    <span className="num text-[13px] text-muted-soft">
                      {t("monitors.config.step", { id: step.id })}
                      {" · "}
                      {t("monitors.config.method")} {step.request.method ?? "GET"}
                    </span>
                    <p className="num mt-0.5 break-all text-[13px]">
                      <span className="text-muted-foreground">
                        {t("monitors.config.requestUrl")}
                      </span>{" "}
                      {step.request.url}
                    </p>
                  </li>
                ))}
              </ul>
              {(spec.source.assertions ?? []).length > 0 && (
                <>
                  <p className="label-line mt-3">{t("monitors.config.assertions")}</p>
                  <ul className="mt-1 divide-y border-t">
                    {(spec.source.assertions ?? []).map((assertion, index) => (
                      <li key={`${assertion.type}-${index}`}
                          className="num break-all py-1.5 text-[13px]">
                        {assertion.type === "json_equals"
                          ? t("monitors.config.assertionEquals", {
                              path: assertion.path ?? "",
                              value: String(assertion.equals ?? ""),
                            })
                          : t("monitors.config.assertionPresent", { path: assertion.path ?? "" })}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {spec.source.pagination && (
                <>
                  <p className="label-line mt-3">{t("monitors.config.pagination")}</p>
                  <p className="num mt-1 break-all text-[13px]">
                    {t("monitors.config.pageParam")} · {spec.source.pagination.page_param ?? "page"}
                    {" · "}
                    {t("monitors.config.pageSize")} · {spec.source.pagination.size ?? "—"}
                    {" · "}
                    {t("monitors.config.stop")} ·{" "}
                    {spec.source.pagination.stop === "total_reached"
                      ? t("monitors.config.stopTotal")
                      : t("monitors.config.stopEmpty")}
                    {" · "}
                    {t("monitors.config.maxPages")} · {spec.source.pagination.max_pages ?? "—"}
                  </p>
                </>
              )}
            </div>
          )}
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
                <li key={`${rule.type ?? "rule"}-${index}`} className="flex gap-3 py-1.5 text-[14px]">
                  <span className="num mt-0.5 w-4 shrink-0 text-[13px] text-muted-soft">
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
              <p className="num mt-1 text-[14px]">
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
                  <li key={label} className="text-[14px]">{label}</li>
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
            <h3 className="label-line">{t("monitors.config.schedule")}</h3>
            <p className="num mt-1 text-[14px]">
              {formatInterval(monitor.interval_seconds)}
              {" · "}
              {formatTimezone(monitor.timezone)}
            </p>
          </div>

          <div>
            <h3 className="label-line">{t("monitors.config.template")}</h3>
            <p className="mt-1 text-[14px]">
              {templateName(monitor) || t("templates.systemDefault")}
            </p>
          </div>

          {(spec?.browser_steps ?? []).length > 0 && (
            <div>
              <h3 className="label-line">{t("monitors.config.browserSteps")}</h3>
              <ul className="mt-1.5 divide-y border-t">
                {(spec?.browser_steps ?? []).map((step, index) => (
                  <li key={`${step.type}-${index}`} className="num break-all py-1.5 text-[13px]">
                    {stepText(step, {
                      wait: t("monitors.step.waitForSelector"),
                      scroll: t("monitors.step.scroll"),
                      next: t("monitors.step.clickNext"),
                    })}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      <details className="border-t border-hairline px-5 py-3">
        <summary className="cursor-pointer list-none text-[13px] text-muted-foreground transition-colors duration-150 select-none hover:text-ink">
          {t("monitors.config.versions")}
        </summary>
        {versions.isPending && <p className="meta mt-2">{t("monitors.loadingShort")}</p>}
        {versions.error && <p className="meta mt-2">{t("common.listError")}</p>}
        <ul className="mt-2 divide-y divide-hairline border-t border-hairline">
          {(versions.data?.items ?? []).map((version) => (
            <li key={version.draft_id} className="space-y-1.5 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex flex-wrap items-center gap-2 text-[13px]">
                  {t("monitors.config.versionValue", { version: version.version })}
                  {version.current && (
                    <Badge tone="success">{t("monitors.config.versionCurrent")}</Badge>
                  )}
                  <span className="num text-[13px] text-muted-soft">
                    {formatDateTime(version.published_at)}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    className="text-[12px] text-muted-soft hover:text-ink hover:underline"
                    onClick={() => setOpenVersion(openVersion === version.draft_id ? null : version.draft_id)}
                  >
                    {openVersion === version.draft_id
                      ? t("monitors.config.versionHide")
                      : t("monitors.config.versionView")}
                  </button>
                  {!version.current && editable && (
                    <button
                      type="button"
                      className="text-[12px] text-primary-active underline-offset-2 hover:underline"
                      onClick={() => onRestore(version.spec)}
                    >
                      {t("monitors.config.versionRestore")}
                    </button>
                  )}
                </span>
              </div>
              {openVersion === version.draft_id && (
                <pre className="code-window mt-2 max-h-64">
                  {JSON.stringify(version.spec, null, 2)}
                </pre>
              )}
            </li>
          ))}
        </ul>
        <ListPagination query={versions} />
      </details>

      <details className="border-t border-hairline px-5 py-3">
        <summary className="cursor-pointer list-none text-[13px] text-muted-foreground transition-colors duration-150 select-none hover:text-ink">
          {t("monitors.config.raw")}
        </summary>
        <pre className="code-window mt-2 max-h-80">
          {raw}
        </pre>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => void copy()}>
          {copied ? <Check strokeWidth={1.5} /> : <Copy strokeWidth={1.5} />}
          {copied ? t("monitors.config.copied") : t("monitors.config.copy")}
        </Button>
      </details>
    </details>
  );
}
