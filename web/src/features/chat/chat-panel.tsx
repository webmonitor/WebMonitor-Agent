"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowDown,
  ArrowUp,
  ChevronRight,
  Loader2,
  Square,
  TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import {
  useCancelRun,
  useConversation,
  useJobDetail,
  useSendMessage,
  useStartConversation,
  type DraftView,
  type JobView,
  type MessageView,
} from "@/lib/api/hooks";
import { CreateMonitorCard } from "@/features/chat/create-monitor-card";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

const ACTIVE = ["queued", "running"];

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function shortId(value: unknown): string | null {
  const text = textValue(value);
  return text ? text.slice(0, 8) : null;
}

/**
 * The job appends a `started` entry and later a terminal entry per tool call, and
 * parallel calls interleave. Pair each terminal entry with the pending entry of the
 * same name so one tool call reads as one line; the request stays from the start.
 */
function mergeSteps(steps: JobView["steps"]) {
  const merged: JobView["steps"] = [];
  const pending = new Map<string, number>();
  for (const step of steps) {
    const index = step.status === "started" ? undefined : pending.get(step.name);
    if (index === undefined) {
      const start = step.status === "started" ? merged.length : undefined;
      merged.push(step);
      if (start !== undefined) pending.set(step.name, start);
      continue;
    }
    merged[index] = { ...step, arguments: step.arguments ?? merged[index].arguments };
    pending.delete(step.name);
  }
  return merged;
}

type Translate = ReturnType<typeof useI18n>["t"];

/** One readable line of the arguments a tool actually received. */
function stepArgumentsSummary(
  step: JobView["steps"][number],
  t: Translate,
  formatMode: (mode?: string | null) => string,
): string | null {
  const args = asRecord(step.arguments);
  if (!args) return null;
  const url = textValue(args.url);
  const request = asRecord(args.request);
  const spec = asRecord(args.spec);
  const draft = shortId(args.draft_id);
  const revision = typeof args.spec_revision === "number" ? args.spec_revision : null;
  switch (step.name) {
    case "analyze_target":
      return [formatMode(textValue(args.collection_mode) ?? undefined), url].filter(Boolean).join(" · ");
    case "probe_target":
    case "capture_network":
      return url;
    case "replay_request":
      return [textValue(request?.method), textValue(request?.url)].filter(Boolean).join(" ");
    case "save_monitor_draft": {
      const fields = Array.isArray(spec?.fields) ? spec.fields.length : null;
      return [
        textValue(spec?.name),
        fields === null ? null : t("chat.tool.fields", { count: fields }),
        draft,
      ].filter(Boolean).join(" · ");
    }
    case "preview_monitor":
    case "request_creation":
      return [
        draft,
        revision === null ? null : t("chat.tool.revision", { revision }),
      ].filter(Boolean).join(" · ") || null;
    default:
      return Object.entries(args)
        .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
        .slice(0, 3)
        .map(([key, value]) => `${key}: ${String(value)}`)
        .join(" · ") || null;
  }
}

function stepResultHint(step: JobView["steps"][number], t: Translate): string | null {
  const result = asRecord(step.result);
  if (!result) return null;
  if (result.truncated === true) return t("chat.tool.truncated");
  const url = textValue(result.final_url);
  if (url) return url;
  if (typeof result.status === "number") return `HTTP ${result.status}`;
  const draft = shortId(result.draft_id);
  if (draft) return draft;
  const job = shortId(result.job_id);
  if (job) return job;
  const warnings = Array.isArray(result.warnings) ? result.warnings.length : 0;
  return warnings ? t("chat.tool.warnings", { count: warnings }) : null;
}

function stepJson(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function StepDot({ status }: { status: string }) {
  return (
    <span
      aria-hidden
      className={`mt-[0.4rem] size-1.5 shrink-0 rounded-full ${
        status === "failed"
          ? "bg-error"
          : status === "succeeded"
            ? "bg-success"
            : "bg-primary animate-pulse"
      }`}
    />
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div>
      <h4 className="label-line">{title}</h4>
      <pre className="code-window mt-1 max-h-64 overflow-auto text-[12px]">
        {stepJson(value)}
      </pre>
    </div>
  );
}

/**
 * One tool call inside the answer, in the order it happened. The summary line
 * carries the concrete request; opening it adds the full request, response and
 * error detail without leaving the conversation.
 */
function ToolCall({ step }: { step: JobView["steps"][number] }) {
  const { t } = useI18n();
  const { errorText, stepLabel, formatDuration, formatMode, statusLabel } = useFormat();
  const [open, setOpen] = useState(false);
  const summary = stepArgumentsSummary(step, t, formatMode);
  const hint = stepResultHint(step, t);
  const details = step.arguments != null || step.result != null
    || step.error_code != null || step.detail != null;

  return (
    <li className="rounded-md border border-hairline bg-surface-soft/40">
      <details
        className="group"
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className="flex cursor-pointer list-none items-start gap-2 px-3 py-2 select-none [&::-webkit-details-marker]:hidden">
          <StepDot status={step.status} />
          <span className="min-w-0 flex-1 leading-5">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className={`text-[13.5px] font-medium ${
                step.status === "failed" ? "text-error" : "text-ink"
              }`}>
                {stepLabel(step.name)}
              </span>
              {summary && (
                <span className="num min-w-0 truncate text-[12.5px] text-muted-soft">
                  {summary}
                </span>
              )}
            </span>
            <span className="num mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px] text-muted-soft">
              <span className={step.status === "failed" ? "text-error" : undefined}>
                {statusLabel(step.status)}
              </span>
              {typeof step.duration_ms === "number" && (
                <span>{formatDuration(step.duration_ms)}</span>
              )}
              {hint && <span className="min-w-0 truncate">{hint}</span>}
            </span>
            {step.error_code && (
              <span className="mt-0.5 block text-[12.5px] text-error">
                {errorText(step.error_code)}
              </span>
            )}
          </span>
          {details && (
            <ChevronRight
              className="mt-0.5 size-3.5 shrink-0 text-muted-soft transition-transform duration-150 group-open:rotate-90"
              strokeWidth={1.5}
            />
          )}
        </summary>
        {open && details && (
          <div className="space-y-2.5 border-t border-hairline px-3 py-2.5">
            {step.arguments != null && (
              <JsonBlock title={t("chat.tool.request")} value={step.arguments} />
            )}
            {step.result != null && (
              <JsonBlock title={t("chat.tool.response")} value={step.result} />
            )}
            {step.detail != null && step.error_code != null && (
              <JsonBlock title={t("chat.tool.errorDetail")} value={step.detail} />
            )}
          </div>
        )}
      </details>
    </li>
  );
}

/** The run's stored usage; read only when the reader opens the trail. */
function RunCost({ jobId }: { jobId: string }) {
  const { t } = useI18n();
  const { formatTokens } = useFormat();
  const detail = useJobDetail(jobId);
  const result = detail.data?.result;
  const model = typeof result?.model === "string" ? result.model : null;
  const usage = result?.usage;
  const total = usage && typeof usage === "object" && "total_tokens" in usage
    && typeof usage.total_tokens === "number" ? usage.total_tokens : null;
  if (total === null || total <= 0) return null;
  const tokens = formatTokens(total);
  return (
    <p className="num mt-2 text-[13px] text-muted-soft">
      {model ? t("chat.cost.usage", { model, tokens }) : t("chat.cost.tokens", { tokens })}
    </p>
  );
}

type TurnPart = { id: string; content: string; at: string | null };

/**
 * A turn is one user message, or every assistant message and tool call produced
 * by one agent job. Tool calls are placed back between the text fragments by
 * their recorded time, so the answer reads in the order it was produced.
 */
type Turn = { id: string; role: string; jobId: string | null; parts: TurnPart[] };

/**
 * One turn is one user message, or every assistant message produced by one agent
 * job. Fragments stay separate so the job's tool calls can sit between them.
 */
function buildTurns(messages: MessageView[]): Turn[] {
  const turns: Turn[] = [];
  for (const message of messages) {
    const last = turns.at(-1);
    const part: TurnPart = { id: message.id, content: message.content, at: message.created_at };
    if (last && message.role === "assistant" && last.role === "assistant"
        && last.jobId === message.job_id) {
      last.parts.push(part);
      continue;
    }
    turns.push({ id: message.id, role: message.role, jobId: message.job_id, parts: [part] });
  }
  return turns;
}

type TimelineBlock =
  | { kind: "text"; content: string }
  | { kind: "step"; step: JobView["steps"][number] };

/** Merge prose fragments and tool calls into the order they actually happened. */
function buildTimeline(parts: TurnPart[], steps: JobView["steps"]): TimelineBlock[] {
  const events = [
    ...parts.filter((part) => part.content.trim()).map((part, index) => ({
      kind: "text" as const,
      at: part.at ? Date.parse(part.at) : Number.POSITIVE_INFINITY,
      order: index * 2,
      content: part.content,
    })),
    ...steps.map((step, index) => ({
      kind: "step" as const,
      at: Date.parse(step.at),
      order: index * 2 + 1,
      step,
    })),
  ];
  events.sort((left, right) => {
    const a = Number.isNaN(left.at) ? Number.POSITIVE_INFINITY : left.at;
    const b = Number.isNaN(right.at) ? Number.POSITIVE_INFINITY : right.at;
    return a === b ? left.order - right.order : a - b;
  });
  const blocks: TimelineBlock[] = [];
  for (const event of events) {
    if (event.kind === "step") {
      blocks.push({ kind: "step", step: event.step });
      continue;
    }
    const last = blocks.at(-1);
    if (last?.kind === "text") {
      last.content = `${last.content}\n\n${event.content}`;
    } else {
      blocks.push({ kind: "text", content: event.content });
    }
  }
  return blocks;
}

/** Assistant prose: no bubble, no avatar — full-width text, the way it reads best. */
function AssistantText({ content }: { content: string }) {
  return (
    <div className="space-y-2.5 text-[15px] leading-[1.7] text-body [&_a]:text-primary-active [&_a]:underline [&_a]:underline-offset-2 [&_blockquote]:border-l-2 [&_blockquote]:border-primary/40 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_code]:rounded-[4px] [&_code]:bg-surface-strong [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[13.5px] [&_code]:text-ink [&_h1]:mt-5 [&_h1]:font-display [&_h1]:text-[24px] [&_h1]:font-normal [&_h1]:tracking-[-0.01em] [&_h2]:mt-5 [&_h2]:font-display [&_h2]:text-[20px] [&_h2]:font-normal [&_h3]:mt-4 [&_h3]:text-[16px] [&_h3]:font-medium [&_hr]:my-4 [&_li]:pl-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:leading-7 [&_pre]:mt-3 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border-0 [&_pre]:bg-surface-dark [&_pre]:p-4 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-[13px] [&_pre_code]:text-on-dark [&_table]:w-full [&_table]:text-[14px] [&_td]:border [&_td]:border-hairline [&_td]:px-2.5 [&_td]:py-1.5 [&_td]:text-[13px] [&_th]:border [&_th]:border-hairline [&_th]:px-2.5 [&_th]:py-1.5 [&_th]:text-left [&_th]:text-[12px] [&_th]:font-medium [&_th]:uppercase [&_th]:tracking-[0.12em] [&_th]:text-muted-foreground [&_ul]:list-disc [&_ul]:pl-5">
      <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
    </div>
  );
}

/** A single dot in place of a spinner: quieter, closer to streaming text. */
function Thinking({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-2.5 text-[15px] text-muted-foreground">
      <span aria-hidden className="size-1.5 shrink-0 animate-pulse rounded-full bg-primary" />
      {label}
    </p>
  );
}


/**
 * One agent job as it reads: prose, then the tools it called at that point, then
 * the prose that followed. A running call stays visible in place.
 */
function AssistantTurn({
  job,
  parts,
  live,
  label,
}: {
  job?: JobView;
  parts: TurnPart[];
  live: boolean;
  label: string;
}) {
  const { t } = useI18n();
  const [usageOpen, setUsageOpen] = useState(false);
  const steps = job ? mergeSteps(job.steps) : [];
  const blocks = buildTimeline(parts, steps);
  const terminal = Boolean(job && !live && !ACTIVE.includes(job.status));

  return (
    <li className="min-w-0 space-y-2.5">
      {blocks.map((block, index) =>
        block.kind === "text" ? (
          <AssistantText key={`text-${index}`} content={block.content} />
        ) : (
          <ToolCall key={`step-${index}-${block.step.name}`} step={block.step} />
        ),
      )}
      {live && blocks.length === 0 && <Thinking label={label} />}
      {terminal && job && steps.length > 0 && (
        <details
          className="group text-[13px] text-muted-soft"
          onToggle={(event) => setUsageOpen(event.currentTarget.open)}
        >
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 select-none transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
            <ChevronRight
              className="size-3.5 transition-transform duration-150 group-open:rotate-90"
              strokeWidth={1.5}
            />
            {t("chat.run.details")}
          </summary>
          {usageOpen && <RunCost jobId={job.id} />}
        </details>
      )}
    </li>
  );
}

export function ChatPanel({
  conversationId,
  drafting = false,
  pendingDraft,
}: {
  conversationId: string | null;
  drafting?: boolean;
  pendingDraft?: DraftView;
}) {
  const router = useRouter();
  const { t } = useI18n();
  const { errorText, stepLabel } = useFormat();
  const conversation = useConversation(conversationId);
  const send = useSendMessage(conversationId ?? "");
  const start = useStartConversation();
  const cancel = useCancelRun(conversationId ?? "");
  const [draft, setDraft] = useState("");
  // Keep the failure as a code so the visible text follows the active locale.
  const [error, setError] = useState<{ code: string | null } | null>(null);
  const [pinned, setPinned] = useState(true);
  const [composerFocused, setComposerFocused] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  const snapshot = conversation.data;
  const agentJobs = snapshot?.jobs.filter((job) => job.kind === "agent");
  const running = agentJobs?.filter((job) => ACTIVE.includes(job.status)).at(-1);
  const lastJob = agentJobs?.at(-1);
  const failed = lastJob?.status === "failed" ? lastJob : undefined;
  const stopped = lastJob?.status === "cancelled" ? lastJob : undefined;
  const limit = snapshot?.limits.message_max_chars ?? 32000;
  const messages = snapshot?.messages ?? [];
  const activeStep = running?.steps.at(-1);
  const jobsById = new Map(agentJobs?.map((job) => [job.id, job]));
  const turns = buildTurns(messages);
  if (running) {
    const livePart: TurnPart = {
      id: `live-${running.id}`,
      content: running.partial_text,
      at: null,
    };
    const last = turns.at(-1);
    if (last?.role === "assistant" && last.jobId === running.id) {
      last.parts.push(livePart);
    } else {
      turns.push({
        id: `running-${running.id}`,
        role: "assistant",
        jobId: running.id,
        parts: [livePart],
      });
    }
  }
  // A run that left no prose still owes the reader its tool trail.
  const shownJobs = new Set(turns.map((turn) => turn.jobId));
  if (lastJob && lastJob.id !== running?.id && lastJob.steps.length > 0
      && !shownJobs.has(lastJob.id)) {
    turns.push({ id: `trail-${lastJob.id}`, role: "assistant", jobId: lastJob.id, parts: [] });
  }

  useEffect(() => {
    if (!pinned) return;
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [pinned, messages.length, running?.partial_text, running?.steps.length]);

  useEffect(() => {
    setPinned(true);
    // Switching conversations never carries the previous draft or failure over.
    setDraft("");
    setError(null);
  }, [conversationId]);

  useEffect(() => {
    const node = composer.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`;
  }, [draft]);

  async function submit() {
    const content = draft.trim();
    if (!content || send.isPending || start.isPending || running) return;
    if (!conversationId && !drafting) return;
    setError(null);
    try {
      if (!conversationId) {
        // The conversation is created together with its first message, so an
        // abandoned draft never leaves an empty conversation behind.
        const conversation = await start.mutateAsync(content);
        setDraft((current) => (current === content ? "" : current));
        router.replace(`/app?conversation=${conversation.id}`);
        return;
      }
      await send.mutateAsync(content);
      setDraft((current) => (current === content ? "" : current));
      // Your own message always brings the conversation back to the latest turn.
      setPinned(true);
    } catch (failure) {
      setError({ code: failure instanceof ApiError ? failure.code : null });
    }
  }

  if (!conversationId && !drafting) {
    return (
      <section className="grid h-full place-items-center px-6">
        <div className="max-w-sm space-y-1.5">
          <h2 className="text-[15px] font-medium">{t("chat.select.title")}</h2>
          <p className="meta leading-5">{t("chat.select.body")}</p>
        </div>
      </section>
    );
  }

  const lastDraft = snapshot?.drafts.at(-1);
  const monitorId = lastDraft?.monitor_id;
  const empty = messages.length === 0 && !running && !pendingDraft;
  const busy = Boolean(running);

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background">
      <header className="flex h-14 shrink-0 items-center gap-3 px-6">
        <div className="mx-auto flex w-full max-w-[46rem] items-center gap-2">
          <h2 className="truncate text-[15px] font-medium text-ink">
            {snapshot?.conversation.title?.trim() || t("chat.newConversation")}
          </h2>
          {monitorId && (
            <Link href={`/app/monitors/${monitorId}`} className="shrink-0">
              <Badge tone={lastDraft?.status === "published" ? "success" : "warning"}>
                {lastDraft?.status === "published"
                  ? t("chat.badge.published")
                  : t("chat.badge.editing")}
              </Badge>
            </Link>
          )}
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <div
          ref={scroller}
          className="h-full overflow-y-auto px-6"
          onScroll={(event) => {
            const node = event.currentTarget;
            setPinned(node.scrollHeight - node.scrollTop - node.clientHeight < 80);
          }}
        >
          <div
            className={`mx-auto w-full max-w-[46rem] py-8 ${
              empty ? "flex min-h-full flex-col justify-center" : ""
            }`}
          >
            {conversationId && conversation.isPending && <p className="meta">{t("chat.loading")}</p>}
            {conversation.error && (
              <p className="t-body-sm text-error" role="alert">
                {t("chat.loadError")}
              </p>
            )}

            {empty && (
              <div className="space-y-6">
                <div className="max-w-[26rem] space-y-2">
                  <h2 className="display-sm">{t("chat.hero.title")}</h2>
                  <p className="t-body mt-3 max-w-[30rem] text-muted-foreground">{t("chat.hero.body")}</p>
                </div>
              </div>
            )}

            <ol className="space-y-6">
              {turns.map((turn) => {
                if (turn.role === "user") {
                  return (
                    <li key={turn.id} className="flex justify-end">
                      <div className="max-w-[85%] rounded-lg bg-card px-4 py-3 text-[15px] leading-7 break-words whitespace-pre-wrap text-ink">
                        {turn.parts.map((part) => part.content).join("\n\n")}
                      </div>
                    </li>
                  );
                }
                const job = turn.jobId ? jobsById.get(turn.jobId) : undefined;
                const live = Boolean(running && turn.jobId === running.id);
                return (
                  <AssistantTurn
                    key={turn.id}
                    job={job}
                    parts={turn.parts}
                    live={live}
                    label={activeStep ? `${stepLabel(activeStep.name)}…` : t("chat.thinking")}
                  />
                );
              })}

              {!running && stopped && (
                <li className="flex items-center gap-2.5 text-[15px] text-muted-foreground">
                  <Square className="size-3.5" strokeWidth={1.5} />
                  {t("chat.stopped")}
                </li>
              )}
              {!running && failed && (
                <li className="flex gap-3 rounded-lg border border-error/30 bg-error/[0.05] px-4 py-3">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-error" strokeWidth={1.5} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[14px] font-medium text-error">{t("chat.failed.title")}</p>
                    <p className="mt-0.5 text-[14px] leading-6 text-muted-foreground">
                      {t("chat.failed.body", { reason: errorText(failed.error_code) })}
                    </p>
                  </div>
                </li>
              )}
              {pendingDraft && conversationId && (
                // The approval surface lives in the stream at every width.
                <li>
                  <CreateMonitorCard conversationId={conversationId} draft={pendingDraft} />
                </li>
              )}
            </ol>
          </div>
        </div>

        {!pinned && messages.length > 0 && (
          <div className="pointer-events-none absolute inset-x-0 bottom-2 flex justify-center">
            <Button
              variant="outline"
              size="icon"
              aria-label={t("chat.scrollToLatest")}
              className="pointer-events-auto size-9 rounded-full border-hairline bg-canvas"
              onClick={() => setPinned(true)}
            >
              <ArrowDown className="size-4" strokeWidth={1.5} />
            </Button>
          </div>
        )}
      </div>

      <div className="shrink-0 px-6 pt-2 pb-4">
        <div className="mx-auto w-full max-w-[46rem]">
          {/* One field: hairline, 12px radius, the ring only while it has focus. */}
          <div className="flex items-end gap-2 rounded-lg border border-input bg-canvas p-1.5 transition-colors duration-150 focus-within:border-primary focus-within:ring-[3px] focus-within:ring-primary/15">
            <textarea
              ref={composer}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onFocus={() => setComposerFocused(true)}
              onBlur={() => setComposerFocused(false)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void submit();
                }
              }}
              rows={1}
              maxLength={limit}
              aria-label={t("chat.composer.label")}
              className="max-h-[12.5rem] min-h-8 flex-1 resize-none bg-transparent px-1.5 py-1 text-[15px] leading-6 outline-none placeholder:text-muted-soft"
              placeholder={
                busy ? t("chat.composer.placeholderBusy") : t("chat.composer.placeholder")
              }
            />
            {busy ? (
              <Button
                size="icon"
                variant="outline"
                aria-label={t("chat.composer.stop")}
                className="size-9 shrink-0 rounded-md"
                onClick={() => cancel.mutate(undefined, {
                  onError: (failure) => setError({ code: failure instanceof ApiError ? failure.code : null }),
                })}
                disabled={cancel.isPending}
              >
                <Square className="size-3.5" />
              </Button>
            ) : (
              <Button
                size="icon"
                aria-label={t("chat.composer.send")}
                className="size-9 shrink-0 rounded-md"
                onClick={() => void submit()}
                disabled={!draft.trim() || send.isPending || start.isPending}
              >
                {send.isPending || start.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <ArrowUp className="size-4" strokeWidth={1.5} />
                )}
              </Button>
            )}
          </div>
          <p className="mt-2 min-h-4 t-caption text-center text-muted-soft">
            {error ? (
              <span className="text-error" role="alert">
                {error.code ? errorText(error.code) : t("chat.sendError")}
              </span>
            ) : draft.length > limit * 0.9 ? (
              t("chat.composer.counter", { count: draft.length, limit })
            ) : composerFocused ? (
              t("chat.composer.hintSend")
            ) : busy ? (
              t("chat.composer.hintBusy")
            ) : (
              t("chat.composer.hintIdle")
            )}
          </p>
        </div>
      </div>
    </section>
  );
}
