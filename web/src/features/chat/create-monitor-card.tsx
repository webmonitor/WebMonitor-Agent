"use client";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, Mail, RefreshCw, Settings2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DraftSettingsPanel } from "@/features/chat/draft-settings-panel";
import { FieldValues, fieldTypes } from "@/features/monitors/field-values";
import { ApiError } from "@/lib/api/client";
import {
  useApproveDraft,
  useConversation,
  useJobDetail,
  useStartPreview,
  type DraftView,
  type JobView,
} from "@/lib/api/hooks";
import {
  parseDeliveryPreview,
  parseExtractionPreview,
  parseSettings,
  parseSpec,
  type DeliveryPreview,
  type ExtractionPreview,
} from "@/lib/api/preview";
import { formatBytes, useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type CardError =
  | { kind: "code"; code: string }
  | { kind: "previewStale" }
  | { kind: "repreview" }
  | { kind: "create" };

function expiresAt(previews: (ExtractionPreview | DeliveryPreview | null)[]): string | null {
  const values = previews.flatMap((preview) => (preview ? [preview.expires_at] : []));
  if (values.length === 0) return null;
  return values.reduce((earliest, value) =>
    new Date(value).getTime() < new Date(earliest).getTime() ? value : earliest);
}

function EvidenceLinks({ draftId, preview }: { draftId: string; preview: ExtractionPreview }) {
  const { t } = useI18n();
  if (preview.evidence_refs.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
      {preview.evidence_refs.map((reference, index) => (
        <a
          key={reference.sha256}
          className="inline-flex items-center gap-1.5 text-[12px] text-muted-soft transition-colors hover:text-ink"
          href={`/api/v1/drafts/${draftId}/evidence/${index}`}
          target="_blank"
          rel="noreferrer"
        >
          {reference.kind === "screenshot"
            ? t("chat.evidence.screenshot")
            : reference.kind === "json"
              ? t("monitors.evidence.json")
              : t("chat.evidence.archive")}
          <span className="num text-[12px]">{formatBytes(reference.size_bytes)}</span>
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
 * what is being read is a record of one collected page plus the mail it produces.
 * Delivery settings live in their own panel; this card never guesses them.
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
    errorText,
    eventLabel,
    fieldLabels,
    formatRelative,
    warningText,
    statusLabel,
  } = useFormat();
  const extraction = parseExtractionPreview(draft.extraction_preview);
  const delivery = parseDeliveryPreview(draft.delivery_preview);
  const spec = parseSpec(draft.spec);
  const settings = parseSettings(draft.settings);
  const approve = useApproveDraft(conversationId);
  const repreview = useStartPreview(conversationId);
  // Errors are kept as codes/kinds so the visible text follows the locale.
  const [error, setError] = useState<CardError | null>(null);
  const [approving, setApproving] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const conversation = useConversation(conversationId);
  const [requestedJob, setRequestedJob] = useState<JobView | null>(null);
  const jobDetail = useJobDetail(requestedJob?.id ?? null);
  // A preview job belongs to the collection contract revision it was collected for.
  const snapshotJob = conversation.data?.jobs.filter(
    (job) =>
      job.kind === "preview" &&
      job.draft_id === draft.id &&
      job.revision === draft.spec_revision,
  ).at(-1);
  const requested = jobDetail.data ?? requestedJob;
  const trackedJob =
    requested?.draft_id === draft.id && requested.revision === draft.spec_revision
      ? requested
      : null;
  const previewJob =
    trackedJob && (!snapshotJob || trackedJob.created_at >= snapshotJob.created_at)
      ? trackedJob
      : snapshotJob;
  const previewBusy =
    repreview.isPending || Boolean(previewJob && ["queued", "running"].includes(previewJob.status));
  const feedback = previewJob && previewJob.status !== "succeeded" ? (
    <p
      role={previewJob.status === "failed" ? "alert" : "status"}
      className={previewJob.status === "failed" ? "text-[13px] text-error" : "meta"}
    >
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
      if (!draft.extraction_preview_hash || !draft.delivery_preview_hash) return;
      await approve.mutateAsync({
        draftId: draft.id,
        specRevision: draft.spec_revision,
        settingsRevision: draft.settings_revision,
        extractionPreviewHash: draft.extraction_preview_hash,
        deliveryPreviewHash: draft.delivery_preview_hash,
      });
      onApproved?.();
    } catch (failure) {
      setError(
        failure instanceof ApiError
          ? failure.code === "preview_expired" ||
            failure.code === "preview_stale" ||
            failure.code === "stale_revision"
            ? { kind: "previewStale" }
            : { kind: "code", code: failure.code }
          : { kind: "create" },
      );
    } finally {
      setApproving(false);
    }
  }

  const labels = fieldLabels(spec?.fields ?? []);
  const editing = Boolean(draft.monitor_id);
  const settingsComplete = Boolean(
    settings && settings.notification_group_ids.length > 0 && settings.schedule,
  );
  const extractionCurrent = Boolean(
    extraction && extraction.spec_revision === draft.spec_revision && draft.extraction_preview_hash,
  );
  const deliveryCurrent = Boolean(
    delivery && delivery.settings_revision === draft.settings_revision && draft.delivery_preview_hash,
  );
  const expiry = expiresAt([extraction, delivery]);
  const expired = expiry ? new Date(expiry).getTime() <= Date.now() : false;
  const mails = delivery?.rendered_emails ?? [];
  const activeEmail = mails.find((email) => email.event_type === selectedEvent) ?? mails[0];
  const warnings = [...(extraction?.warnings ?? []), ...(delivery?.warnings ?? [])].filter(
    (warning, index, all) => all.indexOf(warning) === index,
  );
  const disabled =
    approving ||
    approve.isPending ||
    previewBusy ||
    expired ||
    !extractionCurrent ||
    !deliveryCurrent ||
    !settingsComplete;
  const approveLabel = approving
    ? editing
      ? t("chat.approve.savingEdit")
      : t("chat.approve.saving")
    : editing
      ? t("chat.approve.saveEdit")
      : t("chat.approve.create");

  const settingsControl = (
    <Button
      variant="outline"
      className="w-full"
      aria-expanded={settingsOpen}
      onClick={() => setSettingsOpen((open) => !open)}
    >
      <Settings2 strokeWidth={1.5} />
      {t("settings.open")}
    </Button>
  );

  const settingsPanel = <DraftSettingsPanel draft={draft} onSaved={() => setSettingsOpen(false)} />;

  if (!extraction) {
    return (
      <section className="surface-pad space-y-3">
        <div className="space-y-1">
          <h2 className="t-title">
            {editing ? t("chat.preview.editTitle") : t("chat.preview.title")}
          </h2>
          <p className="t-body-sm text-muted-foreground">{t("chat.preview.body")}</p>
        </div>
        <Button variant="outline" className="w-full" onClick={() => void onRepreview()} disabled={previewBusy}>
          <RefreshCw strokeWidth={1.5} />
          {previewBusy ? t("chat.preview.opening") : t("chat.preview.run")}
        </Button>
        {settingsControl}
        {settingsOpen && settingsPanel}
        {feedback}
        {error && (
          <p className="text-[13px] text-error" role="alert">
            {describeError(error)}
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="surface">
      <header className="space-y-2 border-b border-hairline px-5 py-4">
        <div className="flex items-baseline justify-between gap-2">
          <span className="label-line">
            {expiry ? t("chat.preview.expires", { relative: formatRelative(expiry) }) : ""}
          </span>
          <Badge tone={expired ? "warning" : "brand"}>
            {expired ? t("chat.status.expired") : t("chat.status.pending")}
          </Badge>
        </div>
        <div className="space-y-0.5">
          <h2 className="t-title">
            {editing ? t("chat.approve.editTitle") : t("chat.approve.title")}
          </h2>
          <p className="t-body-sm text-muted-foreground">
            {editing ? t("chat.approve.editBody") : t("chat.approve.body")}
          </p>
        </div>
      </header>

      <div className="space-y-5 px-5 py-4">
        {extraction.source && (
          <div>
            <h3 className="label-line">{t("chat.section.source")}</h3>
            <div className="code-window mt-2 text-[12.5px]">
              <p className="text-on-dark-soft">
                JSON · {t("chat.source.steps", { count: extraction.source.steps.length })}
                {" · "}{t("chat.source.pages", { count: extraction.source.pages })}
                {" · "}{t("chat.source.assertions", { count: extraction.source.assertions.length })}
              </p>
              <ul className="mt-2 divide-y divide-on-dark/10">
                {extraction.source.steps.map((step) => (
                  <li key={step.id} className="break-all py-1.5 text-on-dark">
                    {step.method} {step.url} → {step.status}
                  </li>
                ))}
              </ul>
              {extraction.source.assertions.length > 0 && (
                <p className="mt-2 break-all text-on-dark-soft">
                  {extraction.source.assertions.map((assertion) => `${assertion.path ?? ""} ✓`).join(" · ")}
                </p>
              )}
            </div>
          </div>
        )}
        <div>
          <h3 className="label-line">{t("chat.section.extracted")}</h3>
          <div className="mt-2 rounded-lg border border-hairline bg-canvas p-3.5">
            <FieldValues
              values={extraction.extracted_data}
              labels={labels}
              types={fieldTypes(spec?.fields ?? [])}
              businessKey={spec?.business_key?.item_fields ?? []}
              mode="compact"
              maxItems={3}
            />
          </div>
        </div>

        <div>
          <h3 className="label-line">{t("chat.section.coverage")}</h3>
          <p className="t-body-sm mt-1 text-body">
            {coverageLabel(extraction.coverage.scope)}
            {extraction.coverage.description ? ` · ${extraction.coverage.description}` : ""}
          </p>
        </div>

        <EvidenceLinks draftId={draft.id} preview={extraction} />

        {warnings.length > 0 && (
          <ul className="space-y-1.5 border-l-2 border-warning pl-3 text-[13px] leading-5 text-warning-ink">
            {warnings.map((warning) => (
              <li key={warning} className="flex items-start gap-1.5">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.5} />
                {warningText(warning)}
              </li>
            ))}
          </ul>
        )}

        {activeEmail && mails.length > 0 && (
          <details className="group border-t border-hairline pt-4" open>
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-1.5 text-[13px] text-muted-foreground transition-colors duration-150 hover:text-ink [&::-webkit-details-marker]:hidden">
              <Mail className="size-3.5 shrink-0" strokeWidth={1.5} />
              <span className="shrink-0">{t("chat.mail.preview")}</span>
              <span className="min-w-0 flex-1 truncate text-right text-[13px]">
                {activeEmail.subject}
              </span>
            </summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {mails.map((email) => (
                <Button
                  key={email.event_type}
                  type="button"
                  size="sm"
                  variant={email.event_type === activeEmail.event_type ? "secondary" : "outline"}
                  onClick={() => setSelectedEvent(email.event_type)}
                >
                  {eventLabel(email.event_type)}
                </Button>
              ))}
            </div>
            <iframe
              key={activeEmail.event_type}
              title={t("chat.mail.title")}
              sandbox=""
              className="mt-3 h-72 w-full rounded-md border border-hairline bg-white"
              srcDoc={activeEmail.preview_html ?? activeEmail.html}
            />
          </details>
        )}
      </div>

      <div className="space-y-2.5 border-t border-hairline px-5 py-4">
        <Button className="h-10 w-full" onClick={() => void onApprove()} disabled={disabled}>
          <CheckCircle2 strokeWidth={1.5} />
          {approveLabel}
        </Button>
        {!settingsComplete && (
          <p className="text-[13px] text-warning-ink">{t("format.error.settings_incomplete")}</p>
        )}
        {settingsComplete && !deliveryCurrent && (
          <p className="text-[13px] text-warning-ink">{t("settings.preview.missing")}</p>
        )}
        {settingsControl}
        <button
          type="button"
          className="w-full text-[13px] text-muted-foreground transition-colors hover:text-ink disabled:opacity-45"
          onClick={() => void onRepreview()}
          disabled={previewBusy || approving}
        >
          {previewBusy ? t("chat.approve.repreviewing") : t("chat.approve.repreview")}
        </button>
      </div>

      {settingsOpen && <div className="border-t border-hairline bg-surface-soft px-5 py-4">{settingsPanel}</div>}

      {(feedback || expired || error) && (
        <div className="space-y-1 border-t border-hairline px-5 py-3">
          {feedback}
          {expired && <p className="text-[13px] text-warning-ink">{t("chat.approve.expired")}</p>}
          {error && (
            <p className="text-[13px] text-error" role="alert">
              {describeError(error)}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
