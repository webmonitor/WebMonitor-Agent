"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
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

const EXAMPLE_KEYS = ["chat.examples.price", "chat.examples.notice", "chat.examples.stock"] as const;

/**
 * The job appends a `started` entry and later a terminal entry per tool call, and
 * parallel calls interleave. Pair each terminal entry with the pending entry of the
 * same name so one tool call reads as one line.
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
    merged[index] = step;
    pending.delete(step.name);
  }
  return merged;
}

function StepList({ steps }: { steps: JobView["steps"] }) {
  const { errorText, stepLabel } = useFormat();
  return (
    <ol className="mt-2 space-y-1.5">
      {steps.map((step, index) => (
        <li
          key={`${step.name}-${index}`}
          className={`flex items-start gap-2 ${
            step.status === "failed"
              ? "text-error"
              : step.status === "started"
                ? "text-foreground"
                : "text-muted-foreground"
          }`}
        >
          <span
            aria-hidden
            className={`mt-[0.4rem] size-1.5 shrink-0 rounded-full ${
              step.status === "failed"
                ? "bg-error"
                : step.status === "succeeded"
                  ? "bg-success"
                  : "bg-primary animate-pulse"
            }`}
          />
          <span className="min-w-0 flex-1 leading-5">
            {stepLabel(step.name)}
            {step.error_code && (
              <span className="block text-[11.5px] leading-5 text-error">
                {errorText(step.error_code)}
              </span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

/**
 * The run's trail. While the assistant works it stays open under the current
 * step; once the run is done it folds into one quiet line above the answer.
 */
function WorkLog({ job, active = false }: { job: JobView; active?: boolean }) {
  const { t } = useI18n();
  const { stepLabel } = useFormat();
  const steps = mergeSteps(job.steps);
  if (steps.length === 0) return null;
  const done = steps.filter((step) => step.status === "succeeded").length;
  const failed = steps.filter((step) => step.status === "failed").length;

  if (active) {
    const current = [...steps].reverse().find((step) => step.status === "started") ?? steps.at(-1)!;
    return (
      <div className="text-[12.5px]">
        <p className="flex items-center gap-2 text-muted-foreground">
          <span aria-hidden className="size-1.5 shrink-0 animate-pulse rounded-full bg-primary" />
          <span className="min-w-0 truncate">{stepLabel(current.name)}</span>
          <span className="num ml-auto shrink-0 text-[11px] tabular-nums">
            {done}/{steps.length}
          </span>
        </p>
        <StepList steps={steps} />
      </div>
    );
  }

  return (
    <details className="group text-[12.5px]">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-muted-foreground transition-colors duration-150 select-none hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 transition-transform duration-150 group-open:rotate-90" strokeWidth={1.5} />
        {failed > 0
          ? t("chat.worklog.incomplete", { total: steps.length, failed })
          : t("chat.worklog.view", { total: steps.length })}
      </summary>
      <StepList steps={steps} />
    </details>
  );
}

type Turn = { id: string; role: string; jobId: string | null; content: string };

/**
 * One turn is one user message and everything the assistant said while handling
 * it. Progress messages arrive as separate rows; joining them keeps the turn's
 * prose at normal paragraph rhythm instead of one 32px gap per fragment.
 */
function buildTurns(messages: MessageView[]): Turn[] {
  const turns: Turn[] = [];
  for (const message of messages) {
    const last = turns.at(-1);
    if (last && message.role === "assistant" && last.role === "assistant"
        && last.jobId === message.job_id) {
      last.content = `${last.content}\n\n${message.content}`;
      continue;
    }
    turns.push({ id: message.id, role: message.role, jobId: message.job_id, content: message.content });
  }
  return turns;
}

/** Assistant prose: no bubble, no avatar — full-width text, the way it reads best. */
function AssistantText({ content }: { content: string }) {
  return (
    <div className="space-y-2 text-[15px] leading-7 [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2 [&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_code]:rounded-[0.25rem] [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[13px] [&_h1]:mt-5 [&_h1]:text-[17px] [&_h1]:font-medium [&_h2]:mt-5 [&_h2]:text-[16px] [&_h2]:font-medium [&_h3]:mt-4 [&_h3]:text-[15px] [&_h3]:font-medium [&_hr]:my-4 [&_li]:pl-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:leading-7 [&_pre]:mt-3 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:bg-muted/50 [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_table]:w-full [&_table]:text-[13px] [&_td]:border [&_td]:px-2.5 [&_td]:py-1.5 [&_th]:border [&_th]:bg-muted/50 [&_th]:px-2.5 [&_th]:py-1.5 [&_th]:text-left [&_th]:font-medium [&_ul]:list-disc [&_ul]:pl-5">
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
    const last = turns.at(-1);
    if (last?.role === "assistant" && last.jobId === running.id) {
      last.content = [last.content, running.partial_text].filter(Boolean).join("\n\n");
    } else {
      turns.push({
        id: `running-${running.id}`,
        role: "assistant",
        jobId: running.id,
        content: running.partial_text,
      });
    }
  }
  const shownJobs = new Set(turns.map((turn) => turn.jobId));
  const strayTrail = !running && lastJob && lastJob.status !== "failed"
    && lastJob.status !== "cancelled" && lastJob.steps.length > 0
    && !shownJobs.has(lastJob.id) ? lastJob : undefined;

  useEffect(() => {
    if (!pinned) return;
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [pinned, messages.length, running?.partial_text, running?.steps.length]);

  useEffect(() => {
    setPinned(true);
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
        setDraft("");
        router.replace(`/app?conversation=${conversation.id}`);
        return;
      }
      await send.mutateAsync(content);
      setDraft("");
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
      <header className="flex h-12 shrink-0 items-center gap-3 px-6">
        <div className="mx-auto flex w-full max-w-[46rem] items-center gap-2">
          <h2 className="truncate text-[14px] text-foreground">
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
              <p className="text-sm text-error" role="alert">
                {t("chat.loadError")}
              </p>
            )}

            {empty && (
              <div className="space-y-6">
                <div className="max-w-[26rem] space-y-2">
                  <h2 className="text-[1.25rem] leading-8 font-medium">{t("chat.hero.title")}</h2>
                  <p className="text-[13px] leading-6 text-muted-foreground">{t("chat.hero.body")}</p>
                </div>
                <ul className="max-w-[34rem] divide-y border-y">
                  {EXAMPLE_KEYS.map((exampleKey) => {
                    const example = t(exampleKey);
                    return (
                      <li key={exampleKey}>
                        <button
                          className="group flex w-full items-start gap-3 py-2.5 text-left text-[13px] leading-6 text-muted-foreground transition-colors duration-150 hover:text-foreground"
                          onClick={() => {
                            setDraft(example);
                            composer.current?.focus();
                          }}
                        >
                          <span className="min-w-0 flex-1">{example}</span>
                          <ArrowUpRight
                            className="mt-1 size-3.5 shrink-0 text-muted-foreground/50 transition-colors duration-150 group-hover:text-foreground"
                            strokeWidth={1.5}
                          />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <ol className="space-y-6">
              {turns.map((turn) => {
                if (turn.role === "user") {
                  return (
                    <li key={turn.id} className="flex justify-end">
                      <div className="max-w-[85%] rounded-[0.875rem] bg-muted px-3.5 py-2.5 text-[15px] leading-7 break-words whitespace-pre-wrap">
                        {turn.content}
                      </div>
                    </li>
                  );
                }
                const job = turn.jobId ? jobsById.get(turn.jobId) : undefined;
                const live = Boolean(running && turn.jobId === running.id);
                const trail = job && job.steps.length > 0 && job.id !== failed?.id;
                return (
                  <li key={turn.id} className="min-w-0 space-y-2.5">
                    {trail && <WorkLog job={job} active={live} />}
                    {turn.content ? (
                      <AssistantText content={turn.content} />
                    ) : live && !trail ? (
                      <Thinking
                        label={activeStep ? `${stepLabel(activeStep.name)}…` : t("chat.thinking")}
                      />
                    ) : null}
                  </li>
                );
              })}

              {/* A run that left no prose still owes the reader its trail. */}
              {strayTrail && (
                <li className="min-w-0">
                  <WorkLog job={strayTrail} />
                </li>
              )}

              {!running && stopped && (
                <li className="flex items-center gap-2.5 text-[15px] text-muted-foreground">
                  <Square className="size-3.5" strokeWidth={1.5} />
                  {t("chat.stopped")}
                </li>
              )}
              {!running && failed && (
                <li className="flex gap-3 rounded-[0.875rem] border border-error/25 bg-error/[0.04] px-4 py-3">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-error" strokeWidth={1.5} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-error">{t("chat.failed.title")}</p>
                    <p className="mt-0.5 text-[13px] leading-6 text-muted-foreground">
                      {t("chat.failed.body", { reason: errorText(failed.error_code) })}
                    </p>
                    <WorkLog job={failed} />
                  </div>
                </li>
              )}
              {pendingDraft && conversationId && (
                <li className="xl:hidden">
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
              className="pointer-events-auto size-8 rounded-full bg-card"
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
          <div className="flex items-end gap-2 rounded-[0.75rem] border border-input bg-card p-1.5 transition-colors duration-150 focus-within:border-ring">
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
              className="max-h-[12.5rem] min-h-8 flex-1 resize-none bg-transparent px-1.5 py-1 text-[15px] leading-6 outline-none placeholder:text-muted-foreground/70"
              placeholder={
                busy ? t("chat.composer.placeholderBusy") : t("chat.composer.placeholder")
              }
            />
            {busy ? (
              <Button
                size="icon"
                aria-label={t("chat.composer.stop")}
                className="size-8 shrink-0 rounded-md"
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
                className="size-8 shrink-0 rounded-md"
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
          <p className="mt-2 min-h-4 text-center text-[11px] text-muted-foreground">
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
