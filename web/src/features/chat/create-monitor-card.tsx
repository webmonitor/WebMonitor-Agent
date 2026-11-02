"use client";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, Mail, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useApproveDraft, useConversation, useJobDetail, useStartPreview, type DraftView, type JobView } from "@/lib/api/hooks";
import { parsePreview, parseSpec, type DraftPreview } from "@/lib/api/preview";
import { formatBytes, useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type CardError =
  | { kind: "code"; code: string }
  | { kind: "previewStale" }
  | { kind: "repreview" }
  | { kind: "create" };

function hostOf(url?: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function EvidenceLinks({ draftId, preview }: { draftId: string; preview: DraftPreview }) {
  const { t } = useI18n();
  if (preview.evidence_refs.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
      {preview.evidence_refs.map((reference, index) => (
        <a
          key={reference.sha256}
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors duration-150 hover:text-foreground"
          href={`/api/v1/drafts/${draftId}/evidence/${index}`}
          target="_blank"
          rel="noreferrer"
        >
          {reference.kind === "screenshot"
            ? t("chat.evidence.screenshot")
            : reference.kind === "json"
              ? t("monitors.evidence.json")
              : t("chat.evidence.archive")}
          <span className="num text-[10px]">{formatBytes(reference.size_bytes)}</span>
          <ExternalLink className="size-3.5" strokeWidth={1.5} />
        </a>
      ))}
    </div>
  );
}

/**
 * The confirmation step of the whole product: everything the user is about to
 * turn into a scheduled monitor is shown here before the button is pressed.
 *
 * It is laid out as a report — a ruled header, then labelled blocks — because
 * what is being read is a record of one collected page, not a settings form.
 */
export function CreateMonitorCard({
  conversationId,
  draft,
  onApproved,
}: {
  conversationId: string;
  draft: DraftView;
  onApproved?: () => void;
}) {
  const { t } = useI18n();
  const {
    coverageLabel,
    describeRule,
    describeRules,
    errorText,
    fieldLabels,
    formatInterval,
    formatRelative,
    formatTimezone,
    formatValue,
    warningText,
    statusLabel,
  } = useFormat();
  const preview = parsePreview(draft.preview);
  const spec = parseSpec(draft.spec);
  const approve = useApproveDraft(conversationId);
  const repreview = useStartPreview(conversationId);
  // Errors are kept as codes/kinds so the visible text follows the locale.
  const [error, setError] = useState<CardError | null>(null);
  const [approving, setApproving] = useState(false);
  const conversation = useConversation(conversationId);
  const [requestedJob, setRequestedJob] = useState<JobView | null>(null);
  const jobDetail = useJobDetail(requestedJob?.id ?? null);
  const snapshotJob = conversation.data?.jobs.filter(
    (job) => job.kind === "preview" && job.draft_id === draft.id && job.revision === draft.revision,
  ).at(-1);
  const requested = jobDetail.data ?? requestedJob;
  const trackedJob = requested?.draft_id === draft.id && requested.revision === draft.revision ? requested : null;
  const previewJob = trackedJob && (!snapshotJob || trackedJob.created_at >= snapshotJob.created_at)
    ? trackedJob : snapshotJob;
  const previewBusy = repreview.isPending || Boolean(previewJob && ["queued", "running"].includes(previewJob.status));
  const feedback = previewJob && previewJob.status !== "succeeded" ? (
    <p role={previewJob.status === "failed" ? "alert" : "status"}
      className={previewJob.status === "failed" ? "text-xs text-error" : "meta"}>
      {statusLabel(previewJob.status)}
      {previewJob.error_code ? ` · ${errorText(previewJob.error_code)}` : ""}
    </p>
  ) : null;

  function describeError(failure: CardError): string {
    switch (failure.kind) {
      case "code":
        return errorText(failure.code);
      case "previewStale":
        return t("chat.error.previewStale");
      case "repreview":
        return t("chat.preview.error");
      case "create":
        return t("chat.error.create");
    }
  }

  async function onRepreview() {
    setError(null);
    try {
      setRequestedJob(await repreview.mutateAsync(draft.id));
    } catch (failure) {
      setError(
        failure instanceof ApiError
          ? { kind: "code", code: failure.code }
          : { kind: "repreview" },
      );
    }
  }

  async function onApprove() {
    setError(null);
    setApproving(true);
    try {
      if (!draft.preview_hash) return;
      await approve.mutateAsync({ draftId: draft.id, revision: draft.revision, previewHash: draft.preview_hash });
      onApproved?.();
    } catch (failure) {
      setError(
        failure instanceof ApiError
          ? failure.code === "preview_expired" || failure.code === "preview_stale"
            ? { kind: "previewStale" }
            : { kind: "code", code: failure.code }
          : { kind: "create" },
      );
    } finally {
      setApproving(false);
    }
  }

  const labels = fieldLabels(spec?.fields ?? []);
  const rules = spec?.change_rules?.rules ?? [];
  const simulation = preview?.rule_simulation as {
    triggered?: boolean;
    rule_state?: { predicates?: Record<string, boolean>; aggregate?: boolean };
  } | undefined;
  const predicates = simulation?.rule_state?.predicates ?? {};
  // Change rules have no previous snapshot at preview time; their predicate is
  // false by construction, not because the page failed the rule.
  const historyRules = new Set([
    "text_changed", "number_absolute_change", "number_percent_change",
    "list_added", "list_removed", "list_updated",
  ]);
  const editing = Boolean(draft.monitor_id);
  const expired = preview ? new Date(preview.expires_at).getTime() <= Date.now() : false;
  const disabled = approving || approve.isPending || previewBusy || expired || !preview || !draft.preview_hash;
  const approveLabel = approving
    ? editing
      ? t("chat.approve.savingEdit")
      : t("chat.approve.saving")
    : editing
      ? t("chat.approve.saveEdit")
      : t("chat.approve.create");

  if (!preview) {
    return (
      <section className="surface-pad space-y-3">
        <div className="space-y-1">
          <h2 className="text-[14px] font-medium">
            {editing ? t("chat.preview.editTitle") : t("chat.preview.title")}
          </h2>
          <p className="meta leading-5">{t("chat.preview.body")}</p>
        </div>
        <Button variant="outline" className="w-full" onClick={() => void onRepreview()} disabled={previewBusy}>
          <RefreshCw strokeWidth={1.5} />
          {previewBusy ? t("chat.preview.opening") : t("chat.preview.run")}
        </Button>
        {feedback}
        {error && (
          <p className="text-xs text-error" role="alert">
            {describeError(error)}
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="surface">
      <header className="space-y-2 border-b px-4 py-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="label-line">
            {t("chat.preview.expires", { relative: formatRelative(preview.expires_at) })}
          </span>
          <Badge tone={expired ? "warning" : "brand"}>
            {expired ? t("chat.status.expired") : t("chat.status.pending")}
          </Badge>
        </div>
        <div className="space-y-0.5">
          <h2 className="text-[14px] font-medium">
            {editing ? t("chat.approve.editTitle") : t("chat.approve.title")}
          </h2>
          <p className="meta leading-5">
            {editing ? t("chat.approve.editBody") : t("chat.approve.body")}
          </p>
        </div>
      </header>

      {/* The record header: which page, how often, in which zone. */}
      <div className="space-y-1.5 border-b px-4 py-3">
        <p className="truncate text-[13px] font-medium">
          {spec?.name ?? t("chat.approve.untitled")}
        </p>
        <a
          className="block truncate text-xs text-primary underline-offset-2 hover:underline"
          href={preview.final_url ?? spec?.url}
          target="_blank"
          rel="noreferrer"
        >
          {hostOf(preview.final_url ?? spec?.url)}
        </a>
        <p className="num text-[11px] text-muted-foreground">
          {formatInterval(spec?.schedule?.interval_seconds)}
          {" · "}
          {t("chat.approve.timezone", { zone: formatTimezone(spec?.schedule?.timezone) })}
        </p>
      </div>

      <div className="space-y-4 px-4 py-3">
        {preview.source && (
          <div>
            <h3 className="label-line">{t("chat.section.source")}</h3>
            <p className="num mt-1 text-[12px] text-muted-foreground">
              JSON
              {" · "}
              {t("chat.source.steps", { count: preview.source.steps.length })}
              {" · "}
              {t("chat.source.pages", { count: preview.source.pages })}
              {" · "}
              {t("chat.source.assertions", { count: preview.source.assertions.length })}
            </p>
            <ul className="mt-1.5 divide-y border-t">
              {preview.source.steps.map((step) => (
                <li key={step.id} className="num break-all py-1.5 text-[12px]">
                  {step.method} {step.url} → {step.status}
                </li>
              ))}
            </ul>
            {preview.source.assertions.length > 0 && (
              <p className="num mt-1.5 break-all text-[11px] text-muted-foreground">
                {preview.source.assertions
                  .map((assertion) => `${assertion.path ?? ""} ✓`)
                  .join(" · ")}
              </p>
            )}
          </div>
        )}
        <div>
          <h3 className="label-line">{t("chat.section.extracted")}</h3>
          <dl className="mt-1.5 divide-y">
            {(spec?.fields ?? []).map((field) => (
              <div key={field.name} className="flex items-baseline justify-between gap-3 py-1.5">
                <dt className="shrink-0 text-[12px] text-muted-foreground">{labels[field.name]}</dt>
                <dd className="num min-w-0 truncate text-right text-[13px]">
                  {formatValue(preview.extracted_data[field.name])}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <div>
          <h3 className="label-line">{t("chat.section.coverage")}</h3>
          <p className="mt-1 text-[13px] leading-6">
            {coverageLabel(preview.coverage.scope)}
            {preview.coverage.description ? ` · ${preview.coverage.description}` : ""}
          </p>
        </div>

        <div>
          <h3 className="label-line">{t("chat.section.rules")}</h3>
          <p className="mt-1 text-[13px] leading-6">
            {describeRules(rules, spec?.change_rules?.mode, labels)}
          </p>
          <ul className="mt-1.5 divide-y border-t">
            {rules.map((rule, index) => {
              const value = predicates[String(index)];
              const status = value === true
                ? t("chat.simulation.met")
                : value === false && historyRules.has(rule.type ?? "")
                  ? t("chat.simulation.baseline")
                  : value === false
                    ? t("chat.simulation.unmet")
                    : t("chat.simulation.unknown");
              return (
                <li key={`${rule.type ?? "rule"}-${index}`} className="flex items-baseline justify-between gap-3 py-1.5">
                  <span className="min-w-0 text-[12px] text-muted-foreground">
                    {describeRule(rule, labels)}
                  </span>
                  <span className="num shrink-0 text-[11px]">{status}</span>
                </li>
              );
            })}
          </ul>
          <p className="meta mt-1.5 leading-5">{t("chat.simulation.note")}</p>
        </div>

        <div>
          <h3 className="label-line">{t("chat.section.recipients")}</h3>
          {preview.recipients.length === 0 ? (
            <p className="mt-1 text-[13px] text-warning">{t("chat.recipients.empty")}</p>
          ) : (
            <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
              {preview.recipients.map((recipient) => (
                <li key={recipient} className="num truncate text-[12px] text-muted-foreground">
                  {recipient}
                </li>
              ))}
            </ul>
          )}
        </div>

        <EvidenceLinks draftId={draft.id} preview={preview} />

        {preview.warnings.length > 0 && (
          <ul className="space-y-1 border-l-2 border-warning/40 pl-2.5 text-xs leading-5 text-warning">
            {preview.warnings.map((warning) => (
              <li key={warning} className="flex items-start gap-1.5">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.5} />
                {warningText(warning)}
              </li>
            ))}
          </ul>
        )}

        {preview.rendered_emails.length > 0 && (
          <details className="group border-t pt-3">
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-1.5 text-xs text-muted-foreground transition-colors duration-150 hover:text-foreground [&::-webkit-details-marker]:hidden">
              <Mail className="size-3.5 shrink-0" strokeWidth={1.5} />
              <span className="shrink-0">{t("chat.mail.preview")}</span>
              <span className="min-w-0 flex-1 truncate text-right text-[11px]">
                {preview.rendered_emails[0]?.subject}
              </span>
            </summary>
            {preview.rendered_emails.slice(0, 1).map((email) => (
              <iframe
                key={email.event_type}
                title={t("chat.mail.title")}
                sandbox=""
                className="mt-2 h-64 w-full rounded-lg border bg-white"
                srcDoc={email.preview_html ?? email.html}
              />
            ))}
          </details>
        )}
      </div>

      <div className="space-y-2 border-t px-4 py-3">
        <Button className="w-full" onClick={() => void onApprove()} disabled={disabled}>
          <CheckCircle2 strokeWidth={1.5} />
          {approveLabel}
        </Button>
        <button
          type="button"
          className="w-full text-[12px] text-muted-foreground transition-colors duration-150 hover:text-foreground disabled:opacity-45"
          onClick={() => void onRepreview()}
          disabled={previewBusy || approving}
        >
          {previewBusy ? t("chat.approve.repreviewing") : t("chat.approve.repreview")}
        </button>
      </div>

      {(feedback || expired || error) && (
        <div className="space-y-1 border-t px-4 py-2.5">
          {feedback}
          {expired && <p className="text-xs text-warning">{t("chat.approve.expired")}</p>}
          {error && (
            <p className="text-xs text-error" role="alert">
              {describeError(error)}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
