"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CreateMonitorCard } from "@/features/chat/create-monitor-card";
import { ApiError } from "@/lib/api/client";
import {
  useConversation,
  useDeriveDraft,
  useStartPreview,
  useUpdateDraft,
  type MonitorSpec,
} from "@/lib/api/hooks";
import { monitorSpecSchema } from "@/lib/api/preview";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Session = { conversationId: string; draftId: string; specRevision: number };

/** Field paths the server's collection contract rejects, if any. */
function specIssues(value: unknown): string[] | null {
  const parsed = monitorSpecSchema.safeParse(value);
  if (parsed.success) return null;
  const paths = parsed.error.issues.map((issue) => issue.path.join(".") || "spec");
  return Array.from(new Set(paths));
}

/** The collection contract the API accepts; recipients, cadence and the mail
 *  template are user settings and never part of this document. */
function isMonitorSpec(value: unknown): value is MonitorSpec {
  return monitorSpecSchema.safeParse(value).success;
}

type EditorError =
  | { kind: "parse"; message: string }
  | { kind: "invalid"; fields: string[] }
  | { kind: "code"; code: string | null };

/**
 * A direct editor for the monitor's collection definition. It never writes the
 * monitor: saving replaces an editable draft, a real preview must run, and only
 * the approve endpoint publishes it — the same path the conversation uses.
 * Delivery settings (notification groups, cadence, template) belong to the
 * monitor's settings panel, not to this document.
 */
export function MonitorEditor({
  monitorId,
  spec,
  seedSpec,
  seedToken = 0,
  open,
  onOpenChange,
}: {
  monitorId: string;
  spec: unknown;
  seedSpec?: unknown;
  seedToken?: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const { errorText } = useFormat();
  const derive = useDeriveDraft();
  const update = useUpdateDraft();
  const [session, setSession] = useState<Session | null>(null);
  const [stage, setStage] = useState<"edit" | "review">("edit");
  const [json, setJson] = useState("");
  const [baseline, setBaseline] = useState("");
  const [error, setError] = useState<EditorError | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [saving, setSaving] = useState(false);
  const preparingRef = useRef(false);
  const attemptedRef = useRef(false);
  const lastSeedRef = useRef(seedToken);
  const prepareRef = useRef<() => void>(() => {});
  const preview = useStartPreview(session?.conversationId ?? "");
  const conversation = useConversation(stage === "review" ? session?.conversationId ?? null : null);
  const draft = conversation.data?.drafts.find((item) => item.id === session?.draftId);

  async function prepare() {
    if (preparingRef.current) return;
    preparingRef.current = true;
    setPreparing(true);
    setError(null);
    try {
      const result = await derive.mutateAsync(monitorId);
      const seed = seedSpec ?? spec;
      setSession({
        conversationId: result.conversation_id,
        draftId: result.draft_id,
        specRevision: result.spec_revision,
      });
      setJson(JSON.stringify(seed, null, 2));
      setBaseline(JSON.stringify(seed));
    } catch (failure) {
      setError({ kind: "code", code: failure instanceof ApiError ? failure.code : null });
    } finally {
      preparingRef.current = false;
      setPreparing(false);
    }
  }
  prepareRef.current = prepare;

  // Restoring an older version starts a fresh draft seeded from that spec.
  useEffect(() => {
    if (seedToken === lastSeedRef.current) return;
    lastSeedRef.current = seedToken;
    setSession(null);
    setStage("edit");
    setError(null);
    attemptedRef.current = false;
  }, [seedToken]);

  // Prepare one draft per open; a failure waits for the explicit retry button.
  useEffect(() => {
    if (!open) {
      attemptedRef.current = false;
      return;
    }
    if (attemptedRef.current || session) return;
    attemptedRef.current = true;
    prepareRef.current();
  }, [open, session]);

  const parsed = useMemo(() => {
    try {
      return JSON.stringify(JSON.parse(json));
    } catch {
      return null;
    }
  }, [json]);
  const unchanged = parsed !== null && parsed === baseline;

  async function save() {
    if (!session) return;
    let value: unknown;
    try {
      value = JSON.parse(json);
    } catch (failure) {
      setError({
        kind: "parse",
        message: failure instanceof Error ? failure.message : t("monitors.editor.jsonObject"),
      });
      return;
    }
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      setError({ kind: "parse", message: t("monitors.editor.jsonObject") });
      return;
    }
    if (!isMonitorSpec(value)) {
      setError({ kind: "invalid", fields: specIssues(value) ?? ["spec"] });
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await update.mutateAsync({
        draftId: session.draftId,
        specRevision: session.specRevision,
        spec: value,
      });
      const saved = updated.spec ?? value;
      setSession({ ...session, specRevision: updated.spec_revision });
      setJson(JSON.stringify(saved, null, 2));
      setBaseline(JSON.stringify(saved));
      await preview.mutateAsync(session.draftId);
      setStage("review");
    } catch (failure) {
      if (failure instanceof ApiError) {
        const raw = failure.details.fields;
        const fields = Array.isArray(raw)
          ? raw.map((item: unknown) => String(item).replace(/^body\.spec\.?/, "") || "spec")
          : [];
        setError(failure.code === "validation_failed" && fields.length > 0
          ? { kind: "invalid", fields }
          : { kind: "code", code: failure.code });
      } else {
        setError({ kind: "code", code: null });
      }
    } finally {
      setSaving(false);
    }
  }

  function approved() {
    setSession(null);
    setStage("edit");
    setError(null);
    onOpenChange(false);
  }

  const hint = unchanged ? t("monitors.editor.unchanged") : t("monitors.editor.saveHint");
  const disabled = preparing || saving || !session || !parsed || unchanged;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="pr-6 text-base">{t("monitors.editor.title")}</DialogTitle>
        </DialogHeader>

        {stage === "edit" ? (
          <div className="space-y-3">
            <p className="meta leading-5">{t("monitors.editor.description")}</p>
            <p className="meta leading-5">{t("monitors.editor.specOnly")}</p>

            {preparing && <p className="meta">{t("monitors.editor.preparing")}</p>}

            {error?.kind === "parse" && (
              <p role="alert" className="text-sm text-error">
                {t("monitors.editor.jsonInvalid", { message: error.message })}
              </p>
            )}
            {error?.kind === "invalid" && (
              <div role="alert" className="space-y-1 text-sm text-error">
                <p>{t("monitors.editor.validation", { fields: error.fields.join(", ") })}</p>
              </div>
            )}
            {error?.kind === "code" && (
              <div role="alert" className="space-y-1 text-sm text-error">
                <p>{errorText(error.code)}</p>
                {error.code === "stale_revision" && (
                  <p className="text-xs text-muted-foreground">{t("monitors.editor.reopen")}</p>
                )}
                {error.code === "draft_not_editable" && (
                  <p className="text-xs text-muted-foreground">{t("monitors.editor.reopen")}</p>
                )}
              </div>
            )}

            <textarea
              value={json}
              onChange={(event) => {
                setJson(event.target.value);
                if (error) setError(null);
              }}
              spellCheck={false}
              rows={18}
              aria-label={t("monitors.editor.title")}
              className="w-full resize-y rounded-lg border bg-muted/30 p-3 font-mono text-[12px] leading-relaxed outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />

            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="meta">{session ? hint : ""}</p>
              <div className="flex items-center gap-2">
                {session && (
                  <Link
                    href={`/app?conversation=${session.conversationId}`}
                    className="inline-flex items-center gap-1 text-[12px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                  >
                    {t("monitors.editor.openConversation")}
                    <ExternalLink className="size-3.5" strokeWidth={1.5} />
                  </Link>
                )}
                <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                  {t("monitors.editor.cancel")}
                </Button>
                <Button size="sm" onClick={() => void save()} disabled={disabled}>
                  {saving ? t("monitors.editor.saving") : t("monitors.editor.save")}
                </Button>
              </div>
            </div>

            {error?.kind === "code" && !session && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => {
                  attemptedRef.current = false;
                  prepareRef.current();
                }}
              >
                <RefreshCw strokeWidth={1.5} />
                {t("monitors.editor.retry")}
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1">
              <h3 className="text-[14px] font-medium">{t("monitors.editor.review")}</h3>
              <p className="meta leading-5">{t("monitors.editor.reviewDescription")}</p>
            </div>

            {conversation.error && (
              <p role="alert" className="text-sm text-error">{t("common.listError")}</p>
            )}
            {!conversation.error && !draft && <p className="meta">{t("monitors.loadingShort")}</p>}
            {draft && session && (
              <CreateMonitorCard
                conversationId={session.conversationId}
                draft={draft}
                onApproved={approved}
              />
            )}

            <div className="flex flex-wrap items-center justify-between gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStage("edit")}>
                {t("monitors.editor.backToEdit")}
              </Button>
              {session && (
                <Link
                  href={`/app?conversation=${session.conversationId}`}
                  className="inline-flex items-center gap-1 text-[12px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  {t("monitors.editor.openConversation")}
                  <ExternalLink className="size-3.5" strokeWidth={1.5} />
                </Link>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
