"use client";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
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
export type SnapshotRecord = components["schemas"]["SnapshotRecord"];
export type SnapshotDetail = components["schemas"]["SnapshotDetail"];
export type SpecVersion = components["schemas"]["SpecVersion"];
export type EventView = components["schemas"]["EventView"];
export type Group = components["schemas"]["Group"];
export type Delivery = components["schemas"]["Delivery"];
export type InvitationView = components["schemas"]["InvitationView"];
export type InvitationCreated = components["schemas"]["InvitationCreated"];
export type CreateMonitorResult = components["schemas"]["CreateMonitorResult"];
export type EmailTemplateView = components["schemas"]["EmailTemplateView"];
export type EmailTemplatePreview = components["schemas"]["EmailTemplatePreview"];
export type EmailTemplateProposal = components["schemas"]["EmailTemplateProposal"];
export type EmailTemplateSpec = components["schemas"]["EmailTemplateSpec"];
export type EmailTemplatePatch = components["schemas"]["EmailTemplatePatch"];
export type EmailTemplateConfig = components["schemas"]["EmailTemplateConfig"];
export type DeliverySettings = components["schemas"]["DeliverySettings"];
export type MonitorSpec = components["schemas"]["MonitorSpec"];

export type Page<T> = { items: T[]; total: number };

const ACTIVE = ["queued", "running"];

function newClientMessageId(): string {
  const random = globalThis.crypto?.randomUUID?.();
  return random ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const OVERLAP = 20;
const MAX_PAGES = 20;

function usePagedQuery<T extends { id: string }>(key: readonly unknown[], path: string,
                                                interval: number, limit = 50) {
  const query = useInfiniteQuery({
    queryKey: key,
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => api<Page<T>>(
      `${path}${path.includes("?") ? "&" : "?"}limit=${limit}&offset=${pageParam}`, { signal }),
    // Rows shift between requests, so each page re-reads a few rows behind the
    // last offset; ids decide both "is there more" and the merged list.
    getNextPageParam: (last, pages, lastParam) => {
      if (last.items.length === 0 || pages.length >= MAX_PAGES) return undefined;
      const loaded = pages.reduce((count, page) => count + page.items.length, 0);
      const unique = new Set(pages.flatMap((page) => page.items.map((row) => row.id))).size;
      if (unique >= last.total) return undefined;
      // Never overlap a whole page away: small limits must still move forward.
      const overlap = Math.min(OVERLAP, Math.floor(limit / 2));
      const next = Math.max(0, loaded - overlap);
      return next > lastParam ? next : undefined;
    },
    maxPages: MAX_PAGES,
    // Polling every page keeps the overlap fresh but multiplies background work;
    // once a list spans several pages, refresh only on user actions.
    refetchInterval: (query) => (query.state.data?.pages.length ?? 0) > 1 ? false : interval,
  });
  const data = useMemo(() => query.data ? {
    items: [...new Map(query.data.pages.flatMap((page) => page.items).map((row) => [row.id, row])).values()],
    total: query.data.pages[0]?.total ?? 0,
  } : undefined, [query.data]);
  return { ...query, data };
}

export function useConversations(archived = false) {
  return usePagedQuery<ConversationView>(
    ["conversations", archived ? "archived" : "active"],
    archived ? "/conversations?archived=true" : "/conversations",
    15000,
  );
}

function useConversationArchive(action: "archive" | "restore") {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<ConversationView>(`/conversations/${id}/${action}`, { method: "POST" }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useArchiveConversation() {
  return useConversationArchive("archive");
}

export function useRestoreConversation() {
  return useConversationArchive("restore");
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

export function useMonitors(archived = false, limit = 100) {
  return usePagedQuery<MonitorView>(
    ["monitors", archived ? "archived" : "active", limit],
    archived ? "/monitors?archived=true" : "/monitors",
    15000, limit,
  );
}

export function useMonitor(id: string) {
  return useQuery({
    queryKey: ["monitor", id],
    queryFn: () => api<MonitorDetail>(`/monitors/${id}`),
    refetchInterval: 5000,
  });
}

export function useMonitorJobs(id: string, limit = 10) {
  return usePagedQuery<JobView>(["monitor-jobs", id, limit], `/monitors/${id}/jobs`, 5000, limit);
}

export function useJobDetail(id: string | null) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => api<JobDetail>(`/jobs/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => ACTIVE.includes(query.state.data?.status ?? "") ? 1000 : false,
  });
}

export function useEvents(monitorId?: string, eventType?: string, acknowledged?: boolean) {
  const query = new URLSearchParams();
  if (monitorId) query.set("monitor_id", monitorId);
  if (eventType) query.set("event_type", eventType);
  if (acknowledged !== undefined) query.set("acknowledged", String(acknowledged));
  const suffix = query.toString();
  return usePagedQuery<EventView>(
    ["events", monitorId ?? "all", eventType ?? "all", acknowledged === undefined ? "any" : String(acknowledged)],
    `/events${suffix ? `?${suffix}` : ""}`, 15000);
}

/** The unread badge counts on the server so it matches the filtered list exactly. */
export function useUnreadEventCount() {
  return useQuery({
    queryKey: ["events", "unread-count"],
    queryFn: () => api<Page<EventView>>("/events?acknowledged=false&limit=1"),
    select: (page) => page.total,
    refetchInterval: 15000,
  });
}

export function useSnapshots(monitorId: string) {
  return usePagedQuery<SnapshotRecord>(["snapshots", monitorId],
    `/monitors/${monitorId}/snapshots`, 15000);
}

export function useSnapshot(id: string | null) {
  return useQuery({
    queryKey: ["snapshot", id],
    queryFn: () => api<SnapshotDetail>(`/snapshots/${id}`),
    enabled: Boolean(id),
  });
}

export function useSpecVersions(monitorId: string) {
  return usePagedQuery<SpecVersion>(["spec-versions", monitorId],
    `/monitors/${monitorId}/specs`, 30000);
}

export function useGroups(limit = 100) {
  return usePagedQuery<Group>(["groups", limit], "/notification-groups", 30000, limit);
}

export function useDeliveries(status?: string, monitorId?: string) {
  const query = new URLSearchParams();
  if (status) query.set("status", status);
  if (monitorId) query.set("monitor_id", monitorId);
  const suffix = query.toString();
  return usePagedQuery<Delivery>(
    ["deliveries", status ?? "all", monitorId ?? "all"],
    `/email-deliveries${suffix ? `?${suffix}` : ""}`, 15000);
}

/** A failed or cancelled delivery can be queued again; the server resets the attempt budget. */
export function useRetryDelivery() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<Delivery>(`/email-deliveries/${id}/retry`, { method: "POST" }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["deliveries"] }),
  });
}

export function useStartConversation() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (content: string) =>
      api<ConversationView>("/conversations", {
        method: "POST",
        body: JSON.stringify({
          message: { content, client_message_id: newClientMessageId() },
        }),
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
    mutationFn: ({ draftId, specRevision, settingsRevision, extractionPreviewHash,
                   deliveryPreviewHash }: {
      draftId: string;
      specRevision: number;
      settingsRevision: number;
      extractionPreviewHash: string;
      deliveryPreviewHash: string;
    }) =>
      api<CreateMonitorResult>(`/conversations/${conversationId}/approve`, {
        method: "POST",
        body: JSON.stringify({
          draft_id: draftId,
          spec_revision: specRevision,
          settings_revision: settingsRevision,
          extraction_preview_hash: extractionPreviewHash,
          delivery_preview_hash: deliveryPreviewHash,
        }),
      }),
    onSuccess: (result) => {
      void cache.invalidateQueries({ queryKey: ["conversation", conversationId] });
      void cache.invalidateQueries({ queryKey: ["monitors"] });
      void cache.invalidateQueries({ queryKey: ["monitor", result.monitor_id] });
      void cache.invalidateQueries({ queryKey: ["monitor-jobs", result.monitor_id] });
      void cache.invalidateQueries({ queryKey: ["spec-versions", result.monitor_id] });
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

export function useUpdateDraft() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, specRevision, settingsRevision, spec, settings }: {
      draftId: string;
      specRevision?: number;
      settingsRevision?: number;
      spec?: MonitorSpec;
      settings?: DeliverySettings;
    }) =>
      api<DraftView>(`/drafts/${draftId}`, {
        method: "PUT",
        body: JSON.stringify({
          spec_revision: specRevision ?? null,
          settings_revision: settingsRevision ?? null,
          spec: spec ?? null,
          settings: settings ?? null,
        }),
      }),
    onSuccess: (draft) =>
      void cache.invalidateQueries({ queryKey: ["conversation", draft.conversation_id] }),
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

export function useRenameMonitor() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ monitorId, name }: { monitorId: string; name: string }) =>
      api<MonitorView>(`/monitors/${monitorId}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      }),
    onSuccess: (_data, { monitorId }) => {
      void cache.invalidateQueries({ queryKey: ["monitor", monitorId] });
      void cache.invalidateQueries({ queryKey: ["monitors"] });
    },
  });
}

export function useArchiveMonitor() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (monitorId: string) =>
      api<MonitorView>(`/monitors/${monitorId}/archive`, { method: "POST" }),
    onSuccess: (_data, monitorId) => {
      void cache.invalidateQueries({ queryKey: ["monitor", monitorId] });
      void cache.invalidateQueries({ queryKey: ["monitors"] });
    },
  });
}

export function useRestoreMonitor() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (monitorId: string) =>
      api<MonitorView>(`/monitors/${monitorId}/restore`, { method: "POST" }),
    onSuccess: (_data, monitorId) => {
      void cache.invalidateQueries({ queryKey: ["monitor", monitorId] });
      void cache.invalidateQueries({ queryKey: ["monitors"] });
    },
  });
}

export function useCancelJob() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      api<JobView>(`/jobs/${jobId}/cancel`, { method: "POST" }),
    onSettled: (_data, _error, jobId) => {
      void cache.invalidateQueries({ queryKey: ["job", jobId] });
      void cache.invalidateQueries({ queryKey: ["monitor-jobs"] });
      void cache.invalidateQueries({ queryKey: ["monitor"] });
    },
  });
}

export function useDeriveDraft() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (monitorId: string) =>
      api<{
        conversation_id: string;
        draft_id: string;
        spec_revision: number;
        settings_revision: number;
      }>(`/monitors/${monitorId}/drafts`, { method: "POST" }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useUpdateMonitorSettings() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ monitorId, settings }: { monitorId: string; settings: DeliverySettings }) =>
      api<MonitorDetail>(`/monitors/${monitorId}/settings`, {
        method: "PATCH",
        body: JSON.stringify({ settings }),
      }),
    onSuccess: (_data, { monitorId }) => {
      void cache.invalidateQueries({ queryKey: ["monitor", monitorId] });
      void cache.invalidateQueries({ queryKey: ["monitors"] });
      void cache.invalidateQueries({ queryKey: ["events"] });
    },
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

export function useMembers() {
  return usePagedQuery<AuthProfile>(["members"], "/members", 30000);
}

export function useSetMemberActive() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, active }: { userId: string; active: boolean }) =>
      api<AuthProfile>(`/members/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ active }),
      }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["members"] }),
  });
}

export function useInvitations() {
  return usePagedQuery<InvitationView>(["invitations"], "/members/invitations", 30000);
}

export function useCreateInvitation() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ email, ttlHours }: { email: string; ttlHours: number }) =>
      api<InvitationCreated>("/members/invitations", {
        method: "POST",
        body: JSON.stringify({ email, ttl_hours: ttlHours }),
      }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["invitations"] }),
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

export function useEmailTemplates() {
  return usePagedQuery<EmailTemplateView>(["email-templates"], "/email-templates", 30000);
}

export type EmailTemplateInput = {
  name: string;
  description: string;
  config: EmailTemplateConfig;
};

export function useWriteEmailTemplate() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: EmailTemplateInput }) =>
      api<EmailTemplateView>(id ? `/email-templates/${id}` : "/email-templates", {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["email-templates"] });
      void cache.invalidateQueries({ queryKey: ["conversation"] });
    },
  });
}

export function useDisableEmailTemplate() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<EmailTemplateView>(`/email-templates/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["email-templates"] });
      void cache.invalidateQueries({ queryKey: ["conversation"] });
    },
  });
}

export function useGenerateEmailTemplate() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (description: string) =>
      api<EmailTemplateProposal>("/email-templates/generate", {
        method: "POST",
        body: JSON.stringify({ description }),
      }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["email-templates"] }),
  });
}

export function usePreviewEmailTemplate() {
  return useMutation({
    mutationFn: (config: EmailTemplateConfig) =>
      api<EmailTemplatePreview>("/email-templates/preview", {
        method: "POST",
        body: JSON.stringify(config),
      }),
  });
}
