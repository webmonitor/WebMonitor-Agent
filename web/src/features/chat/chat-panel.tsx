"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowUp, Loader2, Radar, Square } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useCancelRun, useConversation, useSendMessage, type DraftView, type JobView } from "@/lib/api/hooks";
import { CreateMonitorCard } from "@/features/chat/create-monitor-card";
import { errorText, stepLabel } from "@/lib/format";

const ACTIVE = ["queued", "running"];

const EXAMPLES = [
  "监控这个页面的价格，降价 10% 时邮件提醒我",
  "关注公告栏有没有出现新的通知",
  "每天检查一次库存数量，有变化就告诉我",
];

function WorkLog({ job }: { job: JobView }) {
  if (job.steps.length === 0) return null;
  const current = job.steps.at(-1);
  return (
    <details className="mt-2 rounded-lg border border-dashed bg-muted/30 px-3 py-2 text-xs">
      <summary className="cursor-pointer select-none text-muted-foreground">
        助手做了 {job.steps.length} 步 · {current ? stepLabel(current.name) : ""}
      </summary>
      <ol className="mt-2 space-y-1.5">
        {job.steps.map((step, index) => (
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
              <span className="block text-[13px]">{stepLabel(step.name)}</span>
              {(step.error_code || step.detail) && (
                <span className="block break-words text-[11px] text-muted-foreground">
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

function AssistantText({ content }: { content: string }) {
  return (
    <div className="space-y-2 text-[14px] leading-relaxed [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[12px] [&_h3]:mt-3 [&_h3]:text-[13px] [&_h3]:font-semibold [&_li]:ml-4 [&_li]:list-disc [&_ol_li]:list-decimal [&_p]:my-1.5 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:px-2 [&_th]:py-1">
      <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
    </div>
  );
}

export function ChatPanel({
  conversationId,
  pendingDraft,
}: {
  conversationId: string | null;
  pendingDraft?: DraftView;
}) {
  const conversation = useConversation(conversationId);
  const send = useSendMessage(conversationId ?? "");
  const cancel = useCancelRun(conversationId ?? "");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const atBottom = useRef(true);

  const snapshot = conversation.data;
  const running = snapshot?.jobs.filter((job) => ACTIVE.includes(job.status)).at(-1);
  const lastJob = snapshot?.jobs.at(-1);
  const failed = lastJob?.status === "failed" ? lastJob : undefined;
  const limit = snapshot?.limits.message_max_chars ?? 32000;
  const messages = snapshot?.messages ?? [];

  useEffect(() => {
    if (!atBottom.current) return;
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length, running?.partial_text, running?.steps.length]);

  useEffect(() => {
    atBottom.current = true;
  }, [conversationId]);

  useEffect(() => {
    const node = composer.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`;
    // A taller composer cuts into the message area; keep the latest turn in view.
    if (atBottom.current) bottom.current?.scrollIntoView({ block: "end" });
  }, [draft]);

  async function submit() {
    const content = draft.trim();
    if (!content || !conversationId || send.isPending || running) return;
    setError("");
    try {
      await send.mutateAsync(content);
      setDraft("");
      // Your own message always brings the conversation back to the latest turn.
      atBottom.current = true;
      bottom.current?.scrollIntoView({ block: "end" });
    } catch (failure) {
      setError(failure instanceof ApiError ? errorText(failure.code) : "消息没有发出去，请重试。");
    }
  }

  if (!conversationId) {
    return (
      <section className="grid h-full place-items-center px-6">
        <div className="max-w-sm space-y-2 text-center">
          <h2 className="text-lg font-semibold">先选一个对话</h2>
          <p className="meta">左侧「新对话」会打开一个新会话，你可以直接描述想监控的网页。</p>
        </div>
      </section>
    );
  }

  const lastDraft = snapshot?.drafts.at(-1);
  const monitorId = lastDraft?.monitor_id;

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background">
      <header className="flex h-14 shrink-0 items-center border-b bg-card px-5">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="truncate text-sm font-semibold">{snapshot?.conversation.title?.trim() || "新对话"}</h2>
          {monitorId && (
            <Link href={`/app/monitors/${monitorId}`} className="hidden shrink-0 sm:block">
              <Badge tone={lastDraft?.status === "published" ? "success" : "warning"}>
                {lastDraft?.status === "published" ? "监控已创建" : "正在修改"}
              </Badge>
            </Link>
          )}
        </div>
        {running && (
          <Button
            variant="outline"
            size="sm"
            className="h-8 shrink-0"
            onClick={() => void cancel.mutateAsync()}
            disabled={cancel.isPending}
          >
            <Square className="size-3" />
            停止
          </Button>
        )}
        </div>
      </header>

      <div
        className="min-h-0 flex-1 overflow-y-auto px-5"
        onScroll={(event) => {
          const node = event.currentTarget;
          atBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
        }}
      >
        <div
          className={`mx-auto w-full max-w-3xl py-6 ${
            messages.length === 0 && !running ? "flex min-h-full flex-col justify-center" : ""
          }`}
        >
          {conversation.isPending && <p className="meta">正在加载对话…</p>}
          {conversation.error && (
            <p className="text-sm text-error" role="alert">
              对话加载失败，请刷新页面。
            </p>
          )}

          {messages.length === 0 && !running && !pendingDraft && (
            <div className="mt-6 space-y-6">
              <div className="space-y-2">
                <h2 className="text-xl font-semibold tracking-tight">你想盯着哪个网页？</h2>
                <p className="text-sm text-muted-foreground">
                  用平常的话说清楚要看什么、什么情况下提醒你。助手会先真的打开页面确认能取到内容，再由你决定是否开始监控。
                </p>
              </div>
              <ul className="space-y-2">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      className="w-full rounded-xl border bg-card px-4 py-3 text-left text-[13px] text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground"
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

          <ol className="space-y-6">
            {messages.map((message) =>
              message.role === "user" ? (
                <li key={message.id} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[14px] text-accent-foreground">
                    <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  </div>
                </li>
              ) : (
                <li key={message.id} className="flex gap-3">
                  <span
                    aria-hidden
                    className="mt-1 grid size-7 shrink-0 place-items-center rounded-full bg-primary/10"
                  >
                    <Radar className="size-3.5 text-primary" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <AssistantText content={message.content} />
                  </div>
                </li>
              ),
            )}

            {running && (
              <li className="flex gap-3">
                <span
                  aria-hidden
                  className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary/10"
                >
                  <Loader2 className="size-3.5 animate-spin text-primary" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] text-muted-foreground">
                    {running.steps.at(-1) ? `${stepLabel(running.steps.at(-1)!.name)}…` : "正在理解你的要求…"}
                  </p>
                  {running.partial_text && (
                    <div className="mt-1 text-[14px] text-muted-foreground">
                      <AssistantText content={running.partial_text} />
                    </div>
                  )}
                  <WorkLog job={running} />
                </div>
              </li>
            )}

            {!running && failed && (
              <li className="rounded-xl border border-error/25 bg-error/5 px-4 py-3">
                <p className="text-[13px] font-medium text-error">这次没有完成</p>
                <p className="mt-0.5 text-[13px] text-muted-foreground">
                  {errorText(failed.error_code)}。你可以再发一次，或者换一种说法描述需求。
                </p>
                <WorkLog job={failed} />
              </li>
            )}
            {pendingDraft && (
              <li className="xl:hidden">
                <CreateMonitorCard conversationId={conversationId} draft={pendingDraft} />
              </li>
            )}
          </ol>
          <div ref={bottom} className="h-2" />
        </div>
      </div>

      <div className="shrink-0 border-t bg-card px-5 py-3">
        <div className="mx-auto w-full max-w-3xl">
          <div className="rounded-xl border bg-background p-2 transition-colors focus-within:border-ring/60">
            <textarea
              ref={composer}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void submit();
                }
              }}
              rows={1}
              maxLength={limit}
              disabled={Boolean(running)}
              aria-label="描述你想监控的内容"
              className="max-h-[12.5rem] w-full resize-none bg-transparent px-2 py-1.5 text-[14px] outline-none placeholder:text-muted-foreground/70 disabled:opacity-60"
              placeholder={running ? "助手正在处理，稍等或先停止…" : "例如：监控这个页面的价格，降价 10% 时提醒我"}
            />
            <div className="flex items-center justify-between gap-2 px-1 pt-1">
              <span className="text-[11px] text-muted-foreground">
                {draft.length > limit * 0.9 ? `${draft.length}/${limit} 字` : "Enter 发送，Shift + Enter 换行"}
              </span>
              <Button
                size="sm"
                className="h-8"
                onClick={() => void submit()}
                disabled={Boolean(running) || !draft.trim() || send.isPending}
              >
                {send.isPending ? <Loader2 className="animate-spin" /> : <ArrowUp />}
                发送
              </Button>
            </div>
          </div>
          {error && (
            <p className="mt-2 text-xs text-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
