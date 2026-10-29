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
  Radar,
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
} from "@/lib/api/hooks";
import { CreateMonitorCard } from "@/features/chat/create-monitor-card";
import { errorText, stepLabel } from "@/lib/format";

const ACTIVE = ["queued", "running"];

const EXAMPLES = [
  "监控这个页面的价格，降价 10% 时邮件提醒我",
  "关注公告栏有没有出现新的通知",
  "每天检查一次库存数量，有变化就告诉我",
];

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

/** The collapsed "what the assistant did" trail: one line, expandable, no box. */
function WorkLog({ job, open = false }: { job: JobView; open?: boolean }) {
  const steps = mergeSteps(job.steps);
  if (steps.length === 0) return null;
  const failed = steps.filter((step) => step.status === "failed").length;
  return (
    <details open={open} className="group mt-2.5 text-[13px]">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 text-muted-foreground transition-colors select-none hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" />
        {failed > 0 ? `${steps.length} 步，${failed} 步未完成` : `查看 ${steps.length} 步操作`}
      </summary>
      <ol className="mt-2.5 space-y-2 border-l pl-3.5">
        {steps.map((step, index) => (
          <li key={`${step.name}-${index}`} className="flex items-start gap-2">
            <span
              aria-hidden
              className={`mt-1.5 size-1.5 shrink-0 rounded-full ${
                step.status === "failed"
                  ? "bg-error"
                  : step.status === "succeeded"
                    ? "bg-success"
                    : "bg-muted-foreground/40"
              }`}
            />
            <span className="min-w-0 flex-1">
              <span className="block leading-5">{stepLabel(step.name)}</span>
              {(step.error_code || step.detail) && (
                <span className="block break-words text-[12px] text-muted-foreground">
                  {step.error_code ? errorText(step.error_code) : step.detail?.slice(0, 240)}
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

/** Assistant prose: no bubble, no avatar — full-width text, the way ChatGPT reads. */
function AssistantText({ content }: { content: string }) {
  return (
    <div className="space-y-2 text-[15px] leading-7 [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2 [&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_code]:rounded-md [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[13px] [&_h1]:mt-5 [&_h1]:text-[17px] [&_h2]:mt-5 [&_h2]:text-[16px] [&_h3]:mt-4 [&_h3]:text-[15px] [&_h3]:font-semibold [&_hr]:my-4 [&_li]:pl-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:leading-7 [&_pre]:mt-3 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:bg-muted/50 [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_table]:w-full [&_table]:border-collapse [&_table]:text-[13px] [&_td]:border [&_td]:px-2.5 [&_td]:py-1.5 [&_th]:border [&_th]:bg-muted/50 [&_th]:px-2.5 [&_th]:py-1.5 [&_th]:text-left [&_ul]:list-disc [&_ul]:pl-5 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
    </div>
  );
}

/** A single pulsing dot in place of a spinner: quieter, closer to streaming text. */
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
  const conversation = useConversation(conversationId);
  const send = useSendMessage(conversationId ?? "");
  const start = useStartConversation();
  const cancel = useCancelRun(conversationId ?? "");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [pinned, setPinned] = useState(true);
  const [composerFocused, setComposerFocused] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  const snapshot = conversation.data;
  const running = snapshot?.jobs.filter((job) => ACTIVE.includes(job.status)).at(-1);
  const lastJob = snapshot?.jobs.at(-1);
  const failed = lastJob?.status === "failed" ? lastJob : undefined;
  const stopped = lastJob?.status === "cancelled" ? lastJob : undefined;
  const limit = snapshot?.limits.message_max_chars ?? 32000;
  const messages = snapshot?.messages ?? [];
  const activeStep = running?.steps.at(-1);

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
    setError("");
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
      setError(failure instanceof ApiError ? errorText(failure.code) : "消息没有发出去，请重试。");
    }
  }

  if (!conversationId && !drafting) {
    return (
      <section className="grid h-full place-items-center px-6">
        <div className="max-w-sm space-y-2 text-center">
          <h2 className="text-lg font-semibold">先选一个对话</h2>
          <p className="meta">在左侧选择一个已有对话，或点顶部的「新对话」开始新的一个。</p>
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
      <header className="flex h-12 shrink-0 items-center justify-between gap-3 px-4 pt-1 sm:px-6">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-2">
          <h2 className="truncate text-[13px] text-muted-foreground">
            {snapshot?.conversation.title?.trim() || "新对话"}
          </h2>
          {monitorId && (
            <Link href={`/app/monitors/${monitorId}`} className="shrink-0">
              <Badge tone={lastDraft?.status === "published" ? "success" : "warning"}>
                {lastDraft?.status === "published" ? "监控已创建" : "正在修改"}
              </Badge>
            </Link>
          )}
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <div
          ref={scroller}
          className="h-full overflow-y-auto px-4 sm:px-6"
          onScroll={(event) => {
            const node = event.currentTarget;
            setPinned(node.scrollHeight - node.scrollTop - node.clientHeight < 80);
          }}
        >
          <div
            className={`mx-auto w-full max-w-3xl py-6 ${
              empty ? "flex min-h-full flex-col justify-center" : ""
            }`}
          >
            {conversationId && conversation.isPending && <p className="meta">正在加载对话…</p>}
            {conversation.error && (
              <p className="text-sm text-error" role="alert">
                对话加载失败，请刷新页面。
              </p>
            )}

            {empty && (
              <div className="space-y-7">
                <div className="space-y-2.5 text-center">
                  <span
                    aria-hidden
                    className="mx-auto grid size-11 place-items-center rounded-full bg-primary/10"
                  >
                    <Radar className="size-5 text-primary" />
                  </span>
                  <h2 className="text-[1.375rem] font-semibold tracking-tight">
                    你想盯着哪个网页？
                  </h2>
                  <p className="mx-auto max-w-md text-[13px] leading-6 text-muted-foreground">
                    说清楚要看什么、什么情况下提醒你。助手会先打开页面试采集一次，再由你决定是否开始监控。
                  </p>
                </div>
                <ul className="flex flex-wrap justify-center gap-2">
                  {EXAMPLES.map((example) => (
                    <li key={example}>
                      <button
                        className="cursor-pointer rounded-full border bg-card px-3.5 py-2 text-[13px] text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground"
                        onClick={() => {
                          setDraft(example);
                          composer.current?.focus();
                        }}
                      >
                        {example}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <ol className="space-y-7">
              {messages.map((message) =>
                message.role === "user" ? (
                  <li key={message.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-3xl rounded-br-lg bg-muted px-4 py-2.5 text-[15px] leading-7 break-words whitespace-pre-wrap">
                      {message.content}
                    </div>
                  </li>
                ) : (
                  <li key={message.id} className="min-w-0">
                    <AssistantText content={message.content} />
                  </li>
                ),
              )}

              {running && (
                <li className="min-w-0">
                  {running.partial_text ? (
                    <AssistantText content={running.partial_text} />
                  ) : (
                    <Thinking
                      label={
                        activeStep ? `${stepLabel(activeStep.name)}…` : "正在理解你的要求…"
                      }
                    />
                  )}
                  {running.partial_text && activeStep && (
                    <p className="mt-2 text-[13px] text-muted-foreground">
                      {stepLabel(activeStep.name)}…
                    </p>
                  )}
                  <WorkLog job={running} />
                </li>
              )}

              {/* A finished turn keeps its trail available, collapsed. */}
              {!running &&
                lastJob &&
                lastJob.status !== "failed" &&
                lastJob.steps.length > 0 && (
                  <li className="min-w-0">
                    <WorkLog job={lastJob} />
                  </li>
                )}

              {!running && stopped && (
                <li className="flex items-center gap-2.5 text-[15px] text-muted-foreground">
                  <Square className="size-3.5" />
                  这次检查已停止。
                </li>
              )}
              {!running && failed && (
                <li className="flex gap-3 rounded-2xl border border-error/20 bg-error/5 px-4 py-3">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-error" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-error">这次没有完成</p>
                    <p className="mt-0.5 text-[13px] leading-6 text-muted-foreground">
                      {errorText(failed.error_code)}。你可以再发一次，或者换一种说法描述需求。
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
              aria-label="回到最新消息"
              className="pointer-events-auto size-8 rounded-full bg-card shadow-sm"
              onClick={() => setPinned(true)}
            >
              <ArrowDown className="size-4" />
            </Button>
          </div>
        )}
      </div>

      <div className="shrink-0 px-4 pt-2 pb-4 sm:px-6">
        <div className="mx-auto w-full max-w-3xl">
          {/* The rounded band around the box stays transparent; only the box
              itself is a surface, and its ring appears on hover/focus. */}
          <div className="flex items-end gap-2 rounded-[26px] border border-transparent bg-card px-3 py-2 shadow-sm transition-colors hover:border-border/70 focus-within:border-primary/40 focus-within:shadow-md">
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
              aria-label="描述你想监控的内容"
              className="max-h-[12.5rem] min-h-9 flex-1 resize-none bg-transparent px-1 py-1.5 text-[15px] leading-6 outline-none placeholder:text-muted-foreground/70"
              placeholder={busy ? "助手正在处理，可以先继续输入…" : "描述你想监控的内容，例如价格、库存、公告"}
            />
            {busy ? (
              <Button
                size="icon"
                aria-label="停止这次检查"
                className="size-9 shrink-0 rounded-full"
                onClick={() => void cancel.mutateAsync()}
                disabled={cancel.isPending}
              >
                <Square className="size-3.5" />
              </Button>
            ) : (
              <Button
                size="icon"
                aria-label="发送"
                className="size-9 shrink-0 rounded-full"
                onClick={() => void submit()}
                disabled={!draft.trim() || send.isPending || start.isPending}
              >
                {send.isPending || start.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <ArrowUp className="size-4" />
                )}
              </Button>
            )}
          </div>
          <p className="mt-2 min-h-4 text-center text-[11px] text-muted-foreground">
            {error ? (
              <span className="text-error" role="alert">
                {error}
              </span>
            ) : draft.length > limit * 0.9 ? (
              `${draft.length}/${limit} 字`
            ) : composerFocused ? (
              "Enter 发送，Shift + Enter 换行"
            ) : busy ? (
              "助手正在打开页面试采集，可以点右侧按钮停止"
            ) : (
              "助手会先采集一次，再由你确认是否开始定时监控"
            )}
          </p>
        </div>
      </div>
    </section>
  );
}
