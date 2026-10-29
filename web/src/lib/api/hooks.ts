"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type AuthProfile = components["schemas"]["Member"];
export type ConversationView = components["schemas"]["ConversationView"];
export type ConversationSnapshot = components["schemas"]["ConversationSnapshot"];
export type MessageView = components["schemas"]["MessageView"];
export type JobView = components["schemas"]["JobView"];
export type JobDetail = components["schemas"]["JobDetail"];
export type DraftView = components["schemas"]["DraftView"];
export type MonitorView = components["schemas"]["MonitorView"];
export type MonitorDetail = components["schemas"]["MonitorDetail"];
export type EventView = components["schemas"]["EventView"];
export type Group = components["schemas"]["Group"];
export type Delivery = components["schemas"]["Delivery"];
export type CreateMonitorResult = components["schemas"]["CreateMonitorResult"];

export type Page<T> = { items: T[]; total: number };

const ACTIVE = ["queued", "running"];

function newClientMessageId(): string {
  const random = globalThis.crypto?.randomUUID?.();
  return random ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function page<T>(path: string, limit = 50): Promise<Page<T>> {
  return api<Page<T>>(`${path}${path.includes("?") ? "&" : "?"}limit=${limit}&offset=0`);
}

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => page<ConversationView>("/conversations"),
    refetchInterval: 15000,
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: ["conversation", id],
    queryFn: () => api<ConversationSnapshot>(`/conversations/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.jobs.some((job) => ACTIVE.includes(job.status)) ? 1000 : 15000,
  });
}

export function useMonitors() {
  return useQuery({
    queryKey: ["monitors"],
    queryFn: () => page<MonitorView>("/monitors"),
    refetchInterval: 15000,
  });
}

export function useMonitor(id: string) {
  return useQuery({
    queryKey: ["monitor", id],
    queryFn: () => api<MonitorDetail>(`/monitors/${id}`),
    refetchInterval: 5000,
  });
}

export function useMonitorJobs(id: string) {
  return useQuery({
    queryKey: ["monitor-jobs", id],
    queryFn: () => page<JobView>(`/monitors/${id}/jobs`),
    refetchInterval: 5000,
  });
}

export function useJobDetail(id: string | null) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => api<JobDetail>(`/jobs/${id}`),
    enabled: Boolean(id),
  });
}

export function useEvents() {
  return useQuery({
    queryKey: ["events"],
    queryFn: () => page<EventView>("/events"),
    refetchInterval: 15000,
  });
}

export function useGroups() {
  return useQuery({
    queryKey: ["groups"],
    queryFn: () => page<Group>("/notification-groups"),
    refetchInterval: 30000,
  });
}

export function useDeliveries() {
  return useQuery({
    queryKey: ["deliveries"],
    queryFn: () => page<Delivery>("/email-deliveries"),
    refetchInterval: 15000,
  });
}

export function useCreateConversation() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) =>
      api<ConversationView>("/conversations", {
        method: "POST",
        body: JSON.stringify({ title: title ?? null }),
      }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useSendMessage(conversationId: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (content: string) =>
      api<JobView>(`/conversations/${conversationId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content,
          client_message_id: newClientMessageId(),
        }),
      }),
    onSettled: () => {
      void cache.invalidateQueries({ queryKey: ["conversation", conversationId] });
      void cache.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}

export function useCancelRun(conversationId: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: () => api<JobView>(`/conversations/${conversationId}/cancel`, { method: "POST" }),
    onSettled: () => void cache.invalidateQueries({ queryKey: ["conversation", conversationId] }),
  });
}

export function useApproveDraft(conversationId: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, revision }: { draftId: string; revision: number }) =>
      api<CreateMonitorResult>(`/conversations/${conversationId}/approve`, {
        method: "POST",
        body: JSON.stringify({ draft_id: draftId, revision }),
      }),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["conversation", conversationId] });
      void cache.invalidateQueries({ queryKey: ["monitors"] });
    },
  });
}

export function useStartPreview(conversationId: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (draftId: string) =>
      api<JobView>(`/drafts/${draftId}/preview`, { method: "POST" }),
    onSettled: () => void cache.invalidateQueries({ queryKey: ["conversation", conversationId] }),
  });
}

export function usePauseMonitor() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (monitorId: string) =>
      api<MonitorView>(`/monitors/${monitorId}/pause`, { method: "POST" }),
    onSuccess: (_data, monitorId) => {
      void cache.invalidateQueries({ queryKey: ["monitor", monitorId] });
      void cache.invalidateQueries({ queryKey: ["monitors"] });
    },
  });
}

export function useResumeMonitor() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (monitorId: string) =>
      api<MonitorView>(`/monitors/${monitorId}/resume`, { method: "POST" }),
    onSuccess: (_data, monitorId) => {
      void cache.invalidateQueries({ queryKey: ["monitor", monitorId] });
      void cache.invalidateQueries({ queryKey: ["monitors"] });
    },
  });
}

export function useRunNow() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (monitorId: string) =>
      api<JobView>(`/monitors/${monitorId}/run`, { method: "POST" }),
    onSettled: (_data, _error, monitorId) => {
      void cache.invalidateQueries({ queryKey: ["monitor-jobs", monitorId] });
      void cache.invalidateQueries({ queryKey: ["monitor", monitorId] });
    },
  });
}

export function useDeriveDraft() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (monitorId: string) =>
      api<{ conversation_id: string; draft_id: string; revision: number }>(
        `/monitors/${monitorId}/drafts`,
        { method: "POST" },
      ),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useAckEvent() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) =>
      api<EventView>(`/events/${eventId}/acknowledge`, { method: "POST" }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["events"] }),
  });
}

export type GroupInput = { name: string; enabled: boolean; members: { email: string; active: boolean }[] };

export function useWriteGroup() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: GroupInput }) =>
      api<Group>(id ? `/notification-groups/${id}` : "/notification-groups", {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["groups"] }),
  });
}

export function useDeleteGroup() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<Group>(`/notification-groups/${id}`, { method: "DELETE" }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["groups"] }),
  });
}
