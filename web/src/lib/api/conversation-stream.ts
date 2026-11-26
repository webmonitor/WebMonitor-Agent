"use client";

import type { QueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type ConversationSnapshot = components["schemas"]["ConversationSnapshot"];
type MessageView = components["schemas"]["MessageView"];
type MessagePage = {
  items: MessageView[];
  next_cursor: string | null;
  total: number;
};
type StreamListener = (connected: boolean) => void;

type StreamEntry = {
  source: EventSource | null;
  refs: number;
  listeners: Set<StreamListener>;
  failures: number;
  retry: number | null;
};

const conversationStreams = new Map<string, StreamEntry>();

function snapshotFrom(event: Event): ConversationSnapshot {
  const snapshot = JSON.parse((event as MessageEvent).data) as ConversationSnapshot | null;
  if (!snapshot || typeof snapshot.conversation !== "object" || snapshot.conversation === null
      || !Array.isArray(snapshot.messages) || !Array.isArray(snapshot.jobs)
      || !Array.isArray(snapshot.drafts) || typeof snapshot.limits !== "object"
      || snapshot.limits === null) {
    throw new Error("Invalid conversation snapshot");
  }
  return snapshot;
}

function notify(entry: StreamEntry, connected: boolean) {
  for (const listener of [...entry.listeners]) listener(connected);
}

/** Share one authenticated stream and project deltas onto the cached DB snapshot. */
export function subscribeConversationStream(
  id: string,
  cache: QueryClient,
  listener: StreamListener,
): () => void {
  function scheduleReconnect(entry: StreamEntry) {
    if (entry.retry !== null || entry.refs === 0) return;
    const delay = Math.min(15_000, 1000 * 2 ** Math.min(entry.failures, 4));
    entry.failures += 1;
    entry.retry = window.setTimeout(() => {
      entry.retry = null;
      if (entry.refs > 0 && conversationStreams.get(id) === entry) connect(entry);
    }, delay);
  }

  function recover(entry: StreamEntry, source: EventSource) {
    if (entry.source !== source) return;
    source.close();
    entry.source = null;
    notify(entry, false);
    void cache.invalidateQueries({ queryKey: ["conversation", id] });
    scheduleReconnect(entry);
  }

  function connect(entry: StreamEntry) {
    if (entry.source !== null || entry.refs === 0) return;
    const source = new EventSource(`/api/v1/conversations/${id}/stream`);
    entry.source = source;
    source.addEventListener("conversation", (event) => {
      try {
        const snapshot = snapshotFrom(event);
        void cache.cancelQueries({ queryKey: ["conversation", id] });
        cache.setQueryData(["conversation", id], snapshot);
        entry.failures = 0;
        notify(entry, true);
      } catch {
        recover(entry, source);
      }
    });
    source.addEventListener("conversation_delta", (event) => {
      try {
        const delta = JSON.parse((event as MessageEvent).data) as {
          job_id: string;
          partial_text: string;
        } | null;
        if (!delta || typeof delta.job_id !== "string"
            || typeof delta.partial_text !== "string") {
          throw new Error("Invalid conversation delta");
        }
        cache.setQueryData<ConversationSnapshot>(["conversation", id], (current) => {
          if (!current) return current;
          let changed = false;
          const jobs = current.jobs.map((job) => {
            if (job.id !== delta.job_id) return job;
            changed = true;
            return { ...job, partial_text: delta.partial_text };
          });
          return changed ? { ...current, jobs } : current;
        });
      } catch {
        recover(entry, source);
      }
    });
    // Native EventSource retries immediately and cannot reset a malformed event
    // stream. Own the reconnect so every failure has bounded exponential backoff.
    source.addEventListener("error", () => recover(entry, source));
  }

  let entry = conversationStreams.get(id);
  if (!entry) {
    entry = { source: null, refs: 0, listeners: new Set(), failures: 0, retry: null };
    conversationStreams.set(id, entry);
  }
  entry.refs += 1;
  entry.listeners.add(listener);
  if (entry.source === null && entry.retry === null) connect(entry);

  return () => {
    entry.listeners.delete(listener);
    entry.refs -= 1;
    if (entry.refs !== 0) return;
    entry.source?.close();
    entry.source = null;
    window.clearTimeout(entry.retry ?? undefined);
    entry.retry = null;
    if (conversationStreams.get(id) === entry) conversationStreams.delete(id);
  };
}

function chronological(messages: Iterable<MessageView>): MessageView[] {
  const unique = new Map<string, MessageView>();
  for (const message of messages) unique.set(message.id, message);
  return [...unique.values()].sort((left, right) =>
    left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id));
}

type OlderPage = {
  conversationId: string;
  generation: number;
  messages: MessageView[];
  nextCursor: string | null;
};

/** Retain every observed snapshot while older cursor pages extend the history. */
export function useConversationMessages(
  conversationId: string | null | undefined,
  snapshotMessages: readonly MessageView[] | null | undefined,
  hasMore: boolean | null | undefined,
) {
  const [older, setOlder] = useState<OlderPage | null>(null);
  const [failure, setFailure] = useState<{
    conversationId: string;
    generation: number;
    error: Error;
  } | null>(null);
  const [loadingIds, setLoadingIds] = useState<string[]>([]);
  const pending = useRef(new Set<string>());
  const observed = useRef<{
    id: string | null;
    generation: number;
    messages: Map<string, MessageView>;
  }>({ id: null, generation: 0, messages: new Map() });

  const id = conversationId ?? null;
  if (observed.current.id !== id) {
    observed.current = {
      id,
      generation: observed.current.generation + 1,
      messages: new Map(),
    };
  }
  const generation = observed.current.generation;
  const requestKey = id === null ? null : `${id}:${generation}`;
  const activeOlder = older?.conversationId === id && older.generation === generation
    ? older
    : null;
  for (const message of activeOlder?.messages ?? []) {
    observed.current.messages.set(message.id, message);
  }
  for (const message of snapshotMessages ?? []) {
    observed.current.messages.set(message.id, message);
  }
  const messages = useMemo(
    () => chronological(observed.current.messages.values()),
    [id, snapshotMessages, activeOlder],
  );
  const hasOlder = activeOlder ? activeOlder.nextCursor !== null : Boolean(hasMore);
  const isLoading = requestKey !== null && loadingIds.includes(requestKey);
  const error = failure?.conversationId === id && failure.generation === generation
    ? failure.error
    : null;

  const fetchOlder = useCallback(async () => {
    const cursor = activeOlder?.nextCursor ?? messages[0]?.id;
    if (!id || !requestKey || !hasOlder || !cursor || pending.current.has(requestKey)) return;
    pending.current.add(requestKey);
    setLoadingIds((current) => [...current, requestKey]);
    setFailure(null);
    try {
      const query = new URLSearchParams({ cursor, limit: "50" });
      const page = await api<MessagePage>(
        `/conversations/${encodeURIComponent(id)}/messages?${query.toString()}`,
      );
      setOlder((current) => {
        if (current && current.generation > generation) return current;
        return {
          conversationId: id,
          generation,
          messages: chronological([
            ...(current?.conversationId === id && current.generation === generation
              ? current.messages
              : []),
            ...page.items,
          ]),
          nextCursor: page.next_cursor,
        };
      });
    } catch (reason) {
      setFailure((current) => current && current.generation > generation ? current : {
        conversationId: id,
        generation,
        error: reason instanceof Error ? reason : new Error(String(reason)),
      });
    } finally {
      pending.current.delete(requestKey);
      setLoadingIds((current) => current.filter((value) => value !== requestKey));
    }
  }, [activeOlder, generation, hasOlder, id, messages, requestKey]);

  return { messages, isLoading, error, fetchOlder, hasOlder };
}
