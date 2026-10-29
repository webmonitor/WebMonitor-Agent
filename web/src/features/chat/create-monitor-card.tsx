"use client";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, Mail, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useApproveDraft, useStartPreview, type DraftView } from "@/lib/api/hooks";
import { parsePreview, parseSpec, type DraftPreview } from "@/lib/api/preview";
import {
  describeRules,
  errorText,
  fieldLabels,
  formatBytes,
  formatInterval,
  formatRelative,
  formatTimezone,
  formatValue,
  warningText,
} from "@/lib/format";

function hostOf(url?: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function EvidenceLinks({ draftId, preview }: { draftId: string; preview: DraftPreview }) {
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
          {reference.kind === "screenshot" ? "页面截图" : "页面存档"}
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
  const preview = parsePreview(draft.preview);
  const spec = parseSpec(draft.spec);
  const approve = useApproveDraft(conversationId);
  const repreview = useStartPreview(conversationId);
  const [error, setError] = useState("");
  const [approving, setApproving] = useState(false);

  async function onRepreview() {
    setError("");
    try {
      await repreview.mutateAsync(draft.id);
    } catch (failure) {
      setError(failure instanceof ApiError ? errorText(failure.code) : "重新预览没有成功，请稍后再试。");
    }
  }

  async function onApprove() {
    setError("");
    setApproving(true);
    try {
      await approve.mutateAsync({ draftId: draft.id, revision: draft.revision });
    } catch (failure) {
      setError(
        failure instanceof ApiError
          ? failure.code === "preview_expired" || failure.code === "preview_stale"
            ? "预览已过期或收件人已变化，请重新预览后再确认。"
            : errorText(failure.code)
          : "创建没有成功，请重试。",
      );
    } finally {
      setApproving(false);
    }
  }

  const labels = fieldLabels(spec?.fields ?? []);
  const editing = Boolean(draft.monitor_id);
  const expired = preview ? new Date(preview.expires_at).getTime() <= Date.now() : false;
  const disabled = approving || approve.isPending || expired || !preview;

  if (!preview) {
    return (
      <section className="surface-pad space-y-3">
        <div className="space-y-1">
          <h2 className="text-[15px] font-semibold">{editing ? "修改监控" : "准备创建监控"}</h2>
          <p className="meta">助手已经整理好页面设置，还差一次真实预览。</p>
        </div>
        <Button variant="outline" className="w-full" onClick={() => void onRepreview()} disabled={repreview.isPending}>
          <RefreshCw />
          {repreview.isPending ? "正在打开页面…" : "试采集一次"}
        </Button>
        {error && (
          <p className="text-xs text-error" role="alert">
            {error}
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="surface-pad space-y-4">
      <header className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <Badge tone={expired ? "warning" : "brand"}>{expired ? "已过期" : "待确认"}</Badge>
          <span className="meta">{formatRelative(preview.expires_at)}过期</span>
        </div>
        <h2 className="text-[15px] font-semibold">{editing ? "保存监控修改" : "创建监控"}</h2>
        <p className="meta">
          {editing
            ? "保存后会更新现有监控，并重新建立基线。"
            : "下面是一次真实采集的结果，确认后开始定时检查。"}
        </p>
      </header>

      <div className="space-y-2 rounded-lg border bg-muted/40 p-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate text-[13px] font-medium">{spec?.name ?? "未命名监控"}</span>
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
        <p className="meta">时区 {formatTimezone(spec?.schedule?.timezone)}</p>
      </div>

      <div className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">采集到的内容</h3>
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
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">满足条件时通知</h3>
        <p className="text-[13px]">
          {describeRules(spec?.change_rules?.rules ?? [], spec?.change_rules?.mode, labels)}
        </p>
      </div>

      <div className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">收件人</h3>
        {preview.recipients.length === 0 ? (
          <p className="text-[13px] text-warning">还没有收件人，无法发送通知。</p>
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
          <summary className="flex cursor-pointer items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground">
            <Mail className="size-3.5 shrink-0" />
            <span className="shrink-0">预览通知邮件</span>
            <span className="min-w-0 flex-1 truncate text-right">{preview.rendered_emails[0]?.subject}</span>
          </summary>
          {preview.rendered_emails.slice(0, 1).map((email) => (
            <iframe
              key={email.event_type}
              title="通知邮件预览"
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
          {approving ? "正在创建…" : editing ? "保存修改" : "创建监控"}
        </Button>
        <Button
          variant="ghost"
          className="w-full text-muted-foreground"
          onClick={() => void onRepreview()}
          disabled={repreview.isPending}
        >
          <RefreshCw />
          {repreview.isPending ? "正在重新采集…" : "重新预览"}
        </Button>
      </div>

      {expired && (
        <p className="text-xs text-warning">预览已过期，重新预览后才能创建。</p>
      )}
      {error && (
        <p className="text-xs text-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
