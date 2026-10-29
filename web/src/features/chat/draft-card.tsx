"use client";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useApproveDraft, useStartPreview, type DraftView } from "@/lib/api/hooks";
import { parsePreview, parseSpec, type DraftPreview } from "@/lib/api/preview";
import { formatTime, statusLabel } from "@/lib/format";

function EvidenceLinks({ draftId, preview }: { draftId: string; preview: DraftPreview }) {
  if (preview.evidence_refs.length === 0) return null;
  return (
    <p className="flex flex-wrap gap-3 text-xs">
      {preview.evidence_refs.map((reference, index) => (
        <a
          key={reference.sha256}
          className="underline"
          href={`/api/v1/drafts/${draftId}/evidence/${index}`}
          target="_blank"
          rel="noreferrer"
        >
          {reference.kind === "screenshot" ? "截图" : "HTML"} · {Math.round(reference.size_bytes / 1024)} KB
        </a>
      ))}
    </p>
  );
}

export function DraftCard({
  conversationId,
  draft,
}: {
  conversationId: string;
  draft: DraftView;
}) {
  const preview = parsePreview(draft.preview);
  const approve = useApproveDraft(conversationId);
  const repreview = useStartPreview(conversationId);
  const [error, setError] = useState("");
  const [approving, setApproving] = useState(false);

  if (!preview) {
    return (
      <section className="space-y-2 rounded-xl border border-dashed p-4 text-sm">
        <h3>草稿 v{draft.revision}</h3>
        <p className="text-muted-foreground">
          尚无真实预览。可以等待助手完成采集，或直接重新预览。
        </p>
        <Button variant="outline" onClick={() => void onRepreview()} disabled={repreview.isPending}>
          <RefreshCw />
          重新预览
        </Button>
        {error && <p className="text-xs text-error" role="alert">{error}</p>}
      </section>
    );
  }

  const expired = new Date(preview.expires_at).getTime() <= Date.now();

  async function onApprove() {
    setError("");
    setApproving(true);
    try {
      await approve.mutateAsync({ draftId: draft.id, revision: draft.revision });
    } catch (failure) {
      setError(
        failure instanceof ApiError
          ? failure.code === "preview_expired" || failure.code === "preview_stale"
            ? "预览已过期或通知组已变化，请重新预览。"
            : failure.message
          : "确认失败，请重试。",
      );
    } finally {
      setApproving(false);
    }
  }

  async function onRepreview() {
    setError("");
    try {
      await repreview.mutateAsync(draft.id);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "重新预览失败。");
    }
  }

  const spec = parseSpec(draft.spec);

  return (
    <section className="space-y-3 rounded-xl border p-4 text-sm">
      <header className="flex items-start justify-between gap-2">
        <div>
          <h3>监控草稿 v{draft.revision}</h3>
          <p className="text-xs text-muted-foreground">
            预览 {formatTime(preview.created_at)} 生成，{formatTime(preview.expires_at)} 过期
          </p>
        </div>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{statusLabel(draft.status)}</span>
      </header>

      {draft.monitor_id && (
        <p className="text-xs text-muted-foreground">此草稿用于修改已有监控的通知设置。</p>
      )}

      <div>
        <h4 className="mb-1 text-xs font-medium text-muted-foreground">提取字段</h4>
        <ul className="space-y-1">
          {(spec?.fields ?? []).map((field) => (
            <li key={field.name} className="flex items-start justify-between gap-2">
              <span className="font-mono text-xs">{field.name}</span>
              <span className="max-w-[60%] break-words text-right text-xs">
                {JSON.stringify(preview.extracted_data[field.name] ?? null)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h4 className="mb-1 text-xs font-medium text-muted-foreground">覆盖率</h4>
        <p className="text-xs">
          {preview.coverage.scope ?? "bounded"} · {preview.coverage.description ?? ""}
        </p>
      </div>

      <div>
        <h4 className="mb-1 text-xs font-medium text-muted-foreground">收件人</h4>
        <p className="break-words text-xs">{preview.recipients.join("、") || "（无）"}</p>
      </div>

      <EvidenceLinks draftId={draft.id} preview={preview} />

      {preview.warnings.length > 0 && (
        <p className="flex items-start gap-1 text-xs text-warning">
          <AlertTriangle className="mt-0.5 size-3" />
          {preview.warnings.join("、")}
        </p>
      )}

      {preview.rendered_emails.slice(0, 1).map((email) => (
        <details key={email.event_type} className="rounded-lg border">
          <summary className="cursor-pointer px-3 py-2 text-xs">
            邮件预览 · {statusLabel(email.event_type)} · {email.subject}
          </summary>
          <iframe
            title={`邮件预览 ${email.event_type}`}
            sandbox=""
            className="h-64 w-full border-t bg-white"
            srcDoc={email.preview_html ?? email.html}
          />
        </details>
      ))}

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => void onApprove()} disabled={approving || approve.isPending}>
          <CheckCircle2 />
          确认创建
        </Button>
        <Button variant="outline" onClick={() => void onRepreview()} disabled={repreview.isPending}>
          <RefreshCw />
          重新预览
        </Button>
      </div>
      {expired && (
        <p className="text-xs text-warning">预览已过期，请让助手或“重新预览”生成新的预览后再确认。</p>
      )}
      {error && <p className="text-xs text-error" role="alert">{error}</p>}
    </section>
  );
}
