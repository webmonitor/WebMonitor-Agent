"use client";
import { useState } from "react";
import { Plus } from "lucide-react";
import { PageBody, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/empty-state";
import { ListPagination } from "@/components/list-pagination";
import { ApiError } from "@/lib/api/client";
import {
  useDisableEmailTemplate,
  useEmailTemplates,
  type EmailTemplateView,
} from "@/lib/api/hooks";
import { parseTemplateConfig } from "@/lib/api/preview";
import { useAuth } from "@/lib/providers";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { TemplateEditor, TemplatePreviewDialog } from "@/features/templates/template-editor";

export function TemplatesPage() {
  const { user } = useAuth();
  const { t } = useI18n();
  const { errorText } = useFormat();
  const templates = useEmailTemplates();
  const disable = useDisableEmailTemplate();
  const [editing, setEditing] = useState<{ template: EmailTemplateView | null } | null>(null);
  const [previewing, setPreviewing] = useState<EmailTemplateView | null>(null);
  const [confirming, setConfirming] = useState<EmailTemplateView | null>(null);

  const items = templates.data?.items ?? [];
  const disableError = disable.error
    ? disable.error instanceof ApiError
      ? errorText(disable.error.code)
      : t("format.operationFailed")
    : null;

  async function confirmDisable() {
    if (!confirming) return;
    try {
      await disable.mutateAsync(confirming.id);
      setConfirming(null);
    } catch {
      /* The mutation error renders above the list. */
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title={t("templates.title")}
          description={t("templates.subtitle")}
          actions={
            <Button onClick={() => setEditing({ template: null })}>
              <Plus className="size-4" strokeWidth={1.5} />
              {t("templates.new")}
            </Button>
          }
        />

        {templates.isPending && <p className="meta">{t("common.loading")}</p>}

        {!templates.isPending && templates.error && items.length === 0 && (
          <ListPagination query={templates} />
        )}

        {!templates.isPending && !templates.error && items.length === 0 && (
          <EmptyState title={t("templates.empty.title")} description={t("templates.empty.body")} />
        )}

        {disableError && (
          <p role="alert" className="mb-2 text-[13px] text-error">
            {disableError}
          </p>
        )}

        {items.length > 0 && (
          <>
            <ul className="border-t border-hairline divide-y divide-hairline">
              {items.map((template) => {
                const config = parseTemplateConfig(template.config);
                const blockCount = config?.blocks?.length ?? 0;
                const style = config?.style;
                const canManage =
                  user?.role === "admin" || template.created_by_user_id === user?.id;
                return (
                  <li
                    key={template.id}
                    className="flex flex-wrap items-start justify-between gap-3 py-4"
                  >
                    <div className="min-w-0 space-y-1">
                      <p className="truncate text-[15px] font-medium text-ink">{template.name}</p>
                      {template.description && (
                        <p className="meta truncate leading-5">{template.description}</p>
                      )}
                      <p className="meta flex items-center gap-1.5 text-[13px]">
                        {style && (
                          <span aria-hidden className="flex shrink-0 gap-0.5">
                            {[style.accent, style.surface, style.page_background].map(
                              (color, index) =>
                                color ? (
                                  <span
                                    key={index}
                                    className="size-3 rounded-full border border-hairline"
                                    style={{ backgroundColor: color }}
                                  />
                                ) : null,
                            )}
                          </span>
                        )}
                        {t(blockCount === 1 ? "templates.blocks.one" : "templates.blocks", {
                          count: blockCount,
                        })}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-[13px] text-muted-soft hover:text-ink"
                        onClick={() => setPreviewing(template)}
                      >
                        {t("templates.action.preview")}
                      </Button>
                      {canManage && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[13px] text-muted-soft hover:text-ink"
                            onClick={() => setEditing({ template })}
                          >
                            {t("templates.action.edit")}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[13px] text-muted-soft hover:text-ink"
                            disabled={disable.isPending}
                            onClick={() => setConfirming(template)}
                          >
                            {t("templates.action.disable")}
                          </Button>
                        </>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
            <ListPagination query={templates} />
          </>
        )}

        {editing && (
          <TemplateEditor
            key={editing.template?.id ?? "new"}
            template={editing.template}
            onClose={() => setEditing(null)}
          />
        )}

        {previewing && (
          <TemplatePreviewDialog
            key={previewing.id}
            template={previewing}
            onClose={() => setPreviewing(null)}
          />
        )}

        <Dialog
          open={confirming !== null}
          onOpenChange={(value) => {
            if (!value) setConfirming(null);
          }}
        >
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>{t("templates.action.disable")}</DialogTitle>
            </DialogHeader>
            <p className="meta leading-5">{confirming?.name}</p>
            <div className="mt-4 flex justify-end gap-2 border-t border-hairline pt-4">
              <Button variant="ghost" size="sm" onClick={() => setConfirming(null)}>
                {t("common.close")}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={disable.isPending}
                onClick={() => void confirmDisable()}
              >
                {t("templates.action.disable")}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </PageBody>
    </div>
  );
}
