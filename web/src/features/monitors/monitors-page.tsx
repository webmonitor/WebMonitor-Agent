"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Download, Pause, Play, Search, Tag, Upload, X } from "lucide-react";
import { useState, type ChangeEvent, type FormEvent } from "react";
import { EmptyState } from "@/components/empty-state";
import { ListPagination } from "@/components/list-pagination";
import { PageBody, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  useBulkMonitorAction,
  useExportMonitorSpec,
  useImportMonitorSpec,
  useMonitors,
  useUpdateMonitorTags,
  type MonitorSpecDocumentInput,
  type MonitorView,
} from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/client";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

function tagList(value: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const part of value.split(/[,，、\n]/u)) {
    const tag = part.trim();
    if (!tag || seen.has(tag.toLowerCase())) continue;
    seen.add(tag.toLowerCase());
    result.push(tag);
  }
  return result;
}

function TagEditor({ monitor, onClose }: { monitor: MonitorView; onClose: () => void }) {
  const { t } = useI18n();
  const { errorText } = useFormat();
  const [tags, setTags] = useState<string[]>(monitor.tags ?? []);
  const [draft, setDraft] = useState("");
  const [validation, setValidation] = useState<"duplicate" | "limit" | null>(null);
  const update = useUpdateMonitorTags();

  function addTag(event: FormEvent) {
    event.preventDefault();
    const tag = draft.trim();
    if (!tag) return;
    if (tags.some((item) => item.toLowerCase() === tag.toLowerCase())) {
      setValidation("duplicate");
      return;
    }
    if (tags.length >= 20) {
      setValidation("limit");
      return;
    }
    setTags([...tags, tag]);
    setDraft("");
    setValidation(null);
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("management.tags.title", { name: monitor.name })}</DialogTitle>
        <p className="text-[13px] leading-5 text-muted-foreground">{t("management.tags.description")}</p>
      </DialogHeader>
      <div className="mb-4 flex min-h-8 flex-wrap gap-2">
        {tags.length === 0 && <p className="meta">{t("management.tags.empty")}</p>}
        {tags.map((tag) => (
          <Badge key={tag} tone="neutral" className="gap-1 py-1">
            {tag}
            <button
              type="button"
              aria-label={t("management.tags.remove", { tag })}
              className="rounded-full hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setTags(tags.filter((item) => item !== tag))}
            >
              <X className="size-3" strokeWidth={1.5} />
            </button>
          </Badge>
        ))}
      </div>
      <form onSubmit={addTag} className="flex items-end gap-2">
        <label className="min-w-0 flex-1 space-y-1.5">
          <span className="label-line">{t("management.tags.label")}</span>
          <Input
            value={draft}
            maxLength={40}
            placeholder={t("management.tags.placeholder")}
            onChange={(event) => { setDraft(event.target.value); setValidation(null); }}
          />
        </label>
        <Button type="submit" variant="outline" disabled={!draft.trim()}>
          {t("management.tags.add")}
        </Button>
      </form>
      <p className="meta mt-2">{t("management.tags.hint")}</p>
      {validation && (
        <p role="alert" className="mt-3 text-[13px] text-error">
          {t(validation === "duplicate" ? "management.tags.duplicate" : "management.tags.limit")}
        </p>
      )}
      {update.error && <p role="alert" className="mt-3 text-[13px] text-error">{errorText(update.error)}</p>}
      <div className="mt-6 flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>{t("common.close")}</Button>
        <Button
          type="button"
          disabled={update.isPending}
          onClick={() => update.mutate({ monitorId: monitor.id, tags }, { onSuccess: onClose })}
        >
          {update.isPending ? t("management.tags.saving") : t("management.tags.save")}
        </Button>
      </div>
    </>
  );
}

/** Management index: every mutation uses the same monitor and draft commands as detail pages. */
export function MonitorsPage() {
  const { t } = useI18n();
  const { errorText, formatTime, statusLabel } = useFormat();
  const router = useRouter();
  const [keyword, setKeyword] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [applied, setApplied] = useState<{ keyword: string; tags: string[] }>({ keyword: "", tags: [] });
  const [healthStatus, setHealthStatus] = useState<"" | "healthy" | "failed">("");
  const [status, setStatus] = useState<"" | "active" | "paused">("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<MonitorView | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const monitors = useMonitors(false, 50, {
    keyword: applied.keyword,
    tags: applied.tags,
    healthStatus: healthStatus || undefined,
    status: status || undefined,
  });
  const bulk = useBulkMonitorAction();
  const exportSpec = useExportMonitorSpec();
  const importSpec = useImportMonitorSpec();
  const items = monitors.data?.items ?? [];
  const hasFilters = Boolean(applied.keyword || applied.tags.length || healthStatus || status);
  const bulkResults = new Map((bulk.data?.items ?? []).map((item) => [item.monitor_id, item]));
  const succeeded = bulk.data?.items.filter((item) => item.ok).length ?? 0;
  const failed = bulk.data?.items.filter((item) => !item.ok).length ?? 0;

  function clearOperationState() {
    setSelected(new Set());
    bulk.reset();
  }

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setApplied({ keyword: keyword.trim(), tags: tagList(tagsText) });
    clearOperationState();
  }

  function clearFilters() {
    setKeyword("");
    setTagsText("");
    setApplied({ keyword: "", tags: [] });
    setHealthStatus("");
    setStatus("");
    clearOperationState();
  }

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  function runBulk(action: "pause" | "resume") {
    if (selected.size === 0) return;
    bulk.mutate({ monitorIds: [...selected], action }, {
      onSuccess: () => setSelected(new Set()),
    });
  }

  function downloadSpec(monitor: MonitorView) {
    exportSpec.mutate(monitor.id, {
      onSuccess: (specDocument) => {
        const blob = new Blob([`${JSON.stringify(specDocument, null, 2)}\n`], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `monitor-${monitor.id}-v${specDocument.spec_version}.json`;
        anchor.click();
        URL.revokeObjectURL(url);
      },
    });
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setImportError(null);
    importSpec.reset();
    try {
      const document = JSON.parse(await file.text()) as MonitorSpecDocumentInput;
      importSpec.mutate(document, {
        onSuccess: (draft) => router.push(`/app?conversation=${draft.conversation_id}`),
      });
    } catch {
      setImportError(t("management.importInvalidJson"));
    }
  }

  const allSelected = items.length > 0 && items.every((monitor) => selected.has(monitor.id));

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title={t("management.title")}
          description={t("management.description")}
          actions={(
            <Button asChild variant="outline" disabled={importSpec.isPending}>
              <label className="cursor-pointer">
                <Upload strokeWidth={1.5} />
                {importSpec.isPending ? t("management.importing") : t("management.import")}
                <input type="file" accept="application/json,.json" className="sr-only" onChange={importFile} />
              </label>
            </Button>
          )}
        />

        {(importError || importSpec.error) && (
          <p role="alert" className="mb-4 text-sm text-error">
            {importError ?? errorText(importSpec.error)}
          </p>
        )}

        <form onSubmit={applyFilters} className="mb-6 grid gap-3 rounded-lg border border-hairline bg-canvas p-4 lg:grid-cols-5 lg:items-end">
          <label className="space-y-1.5 lg:col-span-2">
            <span className="label-line">{t("management.keyword")}</span>
            <Input value={keyword} maxLength={200} placeholder={t("management.keywordPlaceholder")}
              onChange={(event) => setKeyword(event.target.value)} />
          </label>
          <label className="space-y-1.5">
            <span className="label-line">{t("management.tagFilter")}</span>
            <Input value={tagsText} placeholder={t("management.tagFilterPlaceholder")}
              onChange={(event) => setTagsText(event.target.value)} />
          </label>
          <div className="space-y-1.5">
            <span className="label-line">{t("management.health")}</span>
            <Select label={t("management.health")} value={healthStatus}
              options={[
                { value: "", label: t("management.anyHealth") },
                { value: "healthy", label: statusLabel("healthy") },
                { value: "failed", label: statusLabel("failed") },
              ]}
              onChange={(value) => { setHealthStatus(value as typeof healthStatus); clearOperationState(); }} />
          </div>
          <div className="space-y-1.5">
            <span className="label-line">{t("management.status")}</span>
            <Select label={t("management.status")} value={status}
              options={[
                { value: "", label: t("management.anyStatus") },
                { value: "active", label: statusLabel("active") },
                { value: "paused", label: statusLabel("paused") },
              ]}
              onChange={(value) => { setStatus(value as typeof status); clearOperationState(); }} />
          </div>
          <div className="flex flex-wrap gap-2 lg:col-span-5">
            <Button type="submit" size="sm"><Search strokeWidth={1.5} />{t("management.apply")}</Button>
            {hasFilters && <Button type="button" size="sm" variant="outline" onClick={clearFilters}>
              <X strokeWidth={1.5} />{t("management.clear")}
            </Button>}
          </div>
        </form>

        <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-hairline pb-3">
          <span className="mr-auto text-[13px] text-muted-foreground">
            {t("management.selected", { count: selected.size })}
          </span>
          <Button size="sm" variant="outline" disabled={selected.size === 0 || bulk.isPending}
            onClick={() => runBulk("pause")}>
            <Pause strokeWidth={1.5} />{t("management.pause")}
          </Button>
          <Button size="sm" variant="outline" disabled={selected.size === 0 || bulk.isPending}
            onClick={() => runBulk("resume")}>
            <Play strokeWidth={1.5} />{t("management.resume")}
          </Button>
        </div>

        {bulk.data && (
          <p className={`mb-3 text-[13px] ${failed ? "text-error" : "text-success-ink"}`} role="status">
            {t("management.bulkSummary", { succeeded, failed })}
          </p>
        )}
        {bulk.error && <p role="alert" className="mb-3 text-sm text-error">{errorText(bulk.error)}</p>}
        {exportSpec.error && <p role="alert" className="mb-3 text-sm text-error">{errorText(exportSpec.error)}</p>}
        {monitors.isPending && <p className="meta">{t("common.loading")}</p>}
        {monitors.error && <p role="alert" className="text-sm text-error">{t("common.listError")}</p>}
        {!monitors.isPending && !monitors.error && items.length === 0 && (
          <EmptyState
            title={t(hasFilters ? "management.noMatch.title" : "management.empty.title")}
            description={t(hasFilters ? "management.noMatch.body" : "management.empty.body")}
            action={hasFilters ? (
              <Button variant="outline" size="sm" onClick={clearFilters}>{t("management.clear")}</Button>
            ) : (
              <Button asChild variant="outline" size="sm"><Link href="/app?new=1">{t("management.empty.action")}</Link></Button>
            )}
          />
        )}

        {items.length > 0 && (
          <label className="mb-2 flex items-center gap-2 text-[12px] text-muted-soft">
            <input type="checkbox" checked={allSelected} onChange={() => {
              const next = new Set(selected);
              for (const monitor of items) {
                if (allSelected) next.delete(monitor.id);
                else next.add(monitor.id);
              }
              setSelected(next);
            }} />
            {t("management.selectAll")}
          </label>
        )}

        <ul className="border-t border-hairline">
          {items.map((monitor) => {
            const result = bulkResults.get(monitor.id);
            return (
              <li key={monitor.id} className="border-b border-hairline py-4">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1.5"
                    checked={selected.has(monitor.id)}
                    aria-label={t("management.select", { name: monitor.name })}
                    onChange={() => toggle(monitor.id)}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link href={`/app/monitors/${monitor.id}`}
                        className="truncate text-[15px] font-medium text-ink underline-offset-2 hover:underline">
                        {monitor.name}
                      </Link>
                      <Badge tone={monitor.status === "active" ? "success" : "neutral"}>
                        {statusLabel(monitor.status)}
                      </Badge>
                      <Badge tone={monitor.health_status === "failed" ? "error" : "success"}>
                        {statusLabel(monitor.health_status)}
                      </Badge>
                    </div>
                    <p className="mt-1 truncate text-[12px] text-muted-soft">{monitor.url}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {(monitor.tags ?? []).map((tag) => <Badge key={tag} tone="neutral"><Tag className="size-3" />{tag}</Badge>)}
                    </div>
                    <p className="num mt-2 text-[11px] text-muted-soft">
                      {t("management.version", { version: monitor.spec_version })}
                      {" · "}
                      {t("management.lastSuccess", { time: formatTime(monitor.last_success_at) })}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setEditing(monitor)}>
                      <Tag strokeWidth={1.5} />{t("management.editTags")}
                    </Button>
                    <Button variant="outline" size="sm" disabled={exportSpec.isPending}
                      onClick={() => downloadSpec(monitor)}>
                      <Download strokeWidth={1.5} />
                      {exportSpec.isPending && exportSpec.variables === monitor.id
                        ? t("management.exporting") : t("management.export")}
                    </Button>
                  </div>
                </div>
                {result?.error && (
                  <p role="alert" className="ml-7 mt-2 text-[12px] text-error">
                    {errorText(new ApiError(result.error.code, 409, result.error.message))}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
        <ListPagination query={monitors} />
      </PageBody>

      <Dialog open={Boolean(editing)} onOpenChange={(open) => { if (!open) setEditing(null); }}>
        <DialogContent>
          {editing && <TagEditor key={editing.id} monitor={editing} onClose={() => setEditing(null)} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
