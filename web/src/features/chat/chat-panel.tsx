"use client";
import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Loader2, Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import {
  useCancelRun,
  useConversation,
  useSendMessage,
  type JobView,
} from "@/lib/api/hooks";
import { statusLabel } from "@/lib/format";

const ACTIVE = ["queued", "running"];

function Steps({ job }: { job: JobView }) {
  if (job.steps.length === 0) return null;
  return (
    <details className="mt-2 rounded-lg border bg-muted/40 px-3 py-2 text-xs">
      <summary className="cursor-pointer text-muted-foreground">
        工具进度 · {job.steps.length} 步
      </summary>
      <ol className="mt-2 space-y-1">
        {job.steps.map((step, index) => (
          <li key={`${step.name}-${index}`} className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono">{step.name}</span>
              <span className="text-muted-foreground">
                {statusLabel(step.status)}
                {step.error_code ? ` · ${step.error_code}` : ""}
              </span>
            </div>
            {step.detail && (
              <p className="break-words font-mono text-[11px] text-muted-foreground">
                {step.detail.slice(0, 200)}
              </p>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

export function ChatPanel({ conversationId }: { conversationId: string | null }) {
  const conversation = useConversation(conversationId);
  const send = useSendMessage(conversationId ?? "");
  const cancel = useCancelRun(conversationId ?? "");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  const snapshot = conversation.data;
  const running = snapshot?.jobs.filter((job) => ACTIVE.includes(job.status)).at(-1);
  const limit = snapshot?.limits.message_max_chars ?? 32000;

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [snapshot?.messages.length, running?.partial_text]);

  async function submit() {
    const content = draft.trim();
    if (!content || !conversationId || send.isPending) return;
    setError("");
    try {
      await send.mutateAsync(content);
      setDraft("");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "消息未能发送，请重试。");
    }
  }

  if (!conversationId) {
    return (
      <section className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <h1>用一句话描述你想监控的页面</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          左栏点击“新对话”，助手会真实分析目标页面、保存草稿并预览提取结果，最后由你确认创建。
        </p>
      </section>
    );
  }

  return (
    <section className="flex h-full min-w-0 flex-col">
      <header className="flex items-center justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate">{snapshot?.conversation.title ?? "对话"}</h2>
          <p className="text-xs text-muted-foreground">
            {running ? `助手${statusLabel(running.status)}…` : "轮询快照，无长连接"}
          </p>
        </div>
        {running && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void cancel.mutateAsync()}
            disabled={cancel.isPending}
          >
            <Square />
            停止
          </Button>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {conversation.isPending && <p className="text-sm text-muted-foreground">正在加载对话…</p>}
        {conversation.error && (
          <p className="text-sm text-error" role="alert">{conversation.error.message}</p>
        )}
        <ol className="space-y-3">
          {(snapshot?.messages ?? []).map((message) => (
            <li
              key={message.id}
              className={`rounded-xl px-4 py-3 text-sm ${
                message.role === "user"
                  ? "ml-8 bg-accent text-accent-foreground"
                  : "mr-8 border bg-card"
              }`}
            >
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                {message.role === "user" ? "你" : message.role === "assistant" ? "助手" : "系统"}
              </p>
              {message.role === "assistant" ? (
                <div className="space-y-2 [&_a]:underline [&_code]:font-mono [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:w-full [&_ul]:list-disc [&_ul]:pl-5">
                  <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
              )}
            </li>
          ))}
          {running && (
            <li className="mr-8 rounded-xl border border-dashed bg-card px-4 py-3 text-sm">
              <p className="mb-1 flex items-center gap-2 text-xs font-medium text-muted-foreground">
                <Loader2 className="size-3 animate-spin" />
                助手正在生成
              </p>
              <p className="whitespace-pre-wrap break-words">
                {running.partial_text || "正在请求模型…"}
              </p>
              <Steps job={running} />
            </li>
          )}
          {snapshot?.jobs.at(-1)?.status === "failed" && (
            <li className="mr-8 rounded-xl border border-error/40 bg-card px-4 py-3 text-sm">
              <p className="font-medium text-error">本次运行失败</p>
              <p className="text-muted-foreground">
                {snapshot.jobs.at(-1)?.error_message ?? snapshot.jobs.at(-1)?.error_code}
              </p>
              <Steps job={snapshot.jobs.at(-1)!} />
            </li>
          )}
        </ol>
        <div ref={bottom} />
      </div>

      <div className="border-t px-4 py-3">
        <label htmlFor="composer" className="mb-1 block text-xs text-muted-foreground">
          描述目标页面、要监控的字段与变化条件
        </label>
        <textarea
          id="composer"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) void submit();
          }}
          maxLength={limit}
          rows={3}
          disabled={Boolean(running)}
          className="w-full resize-y rounded-lg border bg-card px-3 py-2 text-sm disabled:opacity-60"
          placeholder="例如：监控 https://example.com/product 的当前价格，每 60 秒检查，下降 10% 通知"
        />
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            {draft.length}/{limit} · ⌘/Ctrl + Enter 发送
          </span>
          <Button onClick={() => void submit()} disabled={Boolean(running) || !draft.trim() || send.isPending}>
            <Send />
            发送
          </Button>
        </div>
        {error && <p className="mt-2 text-sm text-error" role="alert">{error}</p>}
      </div>
    </section>
  );
}
