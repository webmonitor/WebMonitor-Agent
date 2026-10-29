"use client";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, Mail, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useApproveDraft, useStartPreview, type DraftView } from "@/lib/api/hooks";
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
    <div className="flex flex-wrap gap-2">
      {preview.evidence_refs.map((reference, index) => (
        <a
          key={reference.sha256}
          className="chip bg-muted text-muted-foreground hover:text-foreground"
          href={`/api/v1/drafts/${draftId}/evidence/${index}`}
          target="_blank"
          rel="noreferrer"
        >
          {reference.kind === "screenshot"
            ? t("chat.evidence.screenshot")
            : t("chat.evidence.archive")}
          <span className="text-[10px] tabular-nums">{formatBytes(reference.size_bytes)}</span>
          <ExternalLink className="size-3" />
        </a>
      ))}
    </div>
  );
}

/**
 * The confirmation step of the whole product: everything the user is about to
 * turn into a scheduled monitor is shown here before the button is pressed.
 */
export function CreateMonitorCard({
  conversationId,
  draft,
}: {
  conversationId: string;
  draft: DraftView;
}) {
  const { t } = useI18n();
  const {
    describeRules,
    errorText,
    fieldLabels,
    formatInterval,
    formatRelative,
    formatTimezone,
    formatValue,
    warningText,
  } = useFormat();
  const preview = parsePreview(draft.preview);
  const spec = parseSpec(draft.spec);
  const approve = useApproveDraft(conversationId);
  const repreview = useStartPreview(conversationId);
  // Errors are kept as codes/kinds so the visible text follows the locale.
  const [error, setError] = useState<CardError | null>(null);
  const [approving, setApproving] = useState(false);

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
      await repreview.mutateAsync(draft.id);
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
      await approve.mutateAsync({ draftId: draft.id, revision: draft.revision });
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
  const editing = Boolean(draft.monitor_id);
  const expired = preview ? new Date(preview.expires_at).getTime() <= Date.now() : false;
  const disabled = approving || approve.isPending || expired || !preview;
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
          <h2 className="text-[15px] font-semibold">
            {editing ? t("chat.preview.editTitle") : t("chat.preview.title")}
          </h2>
          <p className="meta">{t("chat.preview.body")}</p>
        </div>
        <Button variant="outline" className="w-full" onClick={() => void onRepreview()} disabled={repreview.isPending}>
          <RefreshCw />
          {repreview.isPending ? t("chat.preview.opening") : t("chat.preview.run")}
        </Button>
        {error && (
          <p className="text-xs text-error" role="alert">
            {describeError(error)}
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="surface-pad space-y-4">
      <header className="space-y-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Badge tone={expired ? "warning" : "brand"}>
            {expired ? t("chat.status.expired") : t("chat.status.pending")}
          </Badge>
          <span className="meta">
            {t("chat.preview.expires", { relative: formatRelative(preview.expires_at) })}
          </span>
        </div>
        <h2 className="text-[15px] font-semibold">
          {editing ? t("chat.approve.editTitle") : t("chat.approve.title")}
        </h2>
        <p className="meta">
          {editing ? t("chat.approve.editBody") : t("chat.approve.body")}
        </p>
      </header>

      <div className="space-y-2 rounded-lg border bg-muted/40 p-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="min-w-0 truncate text-[13px] font-medium">
            {spec?.name ?? t("chat.approve.untitled")}
          </span>
          <span className="meta shrink-0 tabular-nums">{formatInterval(spec?.schedule?.interval_seconds)}</span>
        </div>
        <a
          className="block truncate text-xs text-primary underline-offset-2 hover:underline"
          href={preview.final_url ?? spec?.url}
          target="_blank"
          rel="noreferrer"
        >
          {hostOf(preview.final_url ?? spec?.url)}
        </a>
        <p className="meta">
          {t("chat.approve.timezone", { zone: formatTimezone(spec?.schedule?.timezone) })}
        </p>
      </div>

      <div className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {t("chat.section.extracted")}
        </h3>
        <ul className="space-y-1">
          {(spec?.fields ?? []).map((field) => (
            <li key={field.name} className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="shrink-0 text-muted-foreground">{labels[field.name]}</span>
              <span className="min-w-0 truncate text-right font-medium tabular-nums">
                {formatValue(preview.extracted_data[field.name])}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {t("chat.section.rules")}
        </h3>
        <p className="text-[13px]">
          {describeRules(spec?.change_rules?.rules ?? [], spec?.change_rules?.mode, labels)}
        </p>
      </div>

      <div className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {t("chat.section.recipients")}
        </h3>
        {preview.recipients.length === 0 ? (
          <p className="text-[13px] text-warning">{t("chat.recipients.empty")}</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {preview.recipients.map((recipient) => (
              <li key={recipient} className="chip bg-muted text-[11px] text-muted-foreground">
                {recipient}
              </li>
            ))}
          </ul>
        )}
      </div>

      <EvidenceLinks draftId={draft.id} preview={preview} />

      {preview.warnings.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-warning/30 bg-warning/5 p-2.5 text-xs text-warning">
          {preview.warnings.map((warning) => (
            <li key={warning} className="flex items-start gap-1.5">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {warningText(warning)}
            </li>
          ))}
        </ul>
      )}

      {preview.rendered_emails.length > 0 && (
        <details className="group rounded-lg border">
          <summary className="flex cursor-pointer flex-wrap items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground">
            <Mail className="size-3.5 shrink-0" />
            <span className="shrink-0">{t("chat.mail.preview")}</span>
            <span className="min-w-0 flex-1 truncate text-right">{preview.rendered_emails[0]?.subject}</span>
          </summary>
          {preview.rendered_emails.slice(0, 1).map((email) => (
            <iframe
              key={email.event_type}
              title={t("chat.mail.title")}
              sandbox=""
              className="h-64 w-full border-t bg-white"
              srcDoc={email.preview_html ?? email.html}
            />
          ))}
        </details>
      )}

      <div className="space-y-2">
        <Button className="w-full" onClick={() => void onApprove()} disabled={disabled}>
          <CheckCircle2 />
          {approveLabel}
        </Button>
        <Button
          variant="ghost"
          className="w-full text-muted-foreground"
          onClick={() => void onRepreview()}
          disabled={repreview.isPending}
        >
          <RefreshCw />
          {repreview.isPending ? t("chat.approve.repreviewing") : t("chat.approve.repreview")}
        </Button>
      </div>

      {expired && <p className="text-xs text-warning">{t("chat.approve.expired")}</p>}
      {error && (
        <p className="text-xs text-error" role="alert">
          {describeError(error)}
        </p>
      )}
    </section>
  );
}
