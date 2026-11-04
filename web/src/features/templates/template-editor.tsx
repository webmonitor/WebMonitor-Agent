"use client";
import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import {
  useGenerateEmailTemplate,
  usePreviewEmailTemplate,
  useWriteEmailTemplate,
  type EmailTemplateConfig,
  type EmailTemplateView,
} from "@/lib/api/hooks";
import {
  parseTemplateConfig,
  type EmailTemplateConfigView,
  type RenderedEmailView,
  type TemplateBlockView,
} from "@/lib/api/preview";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

const TEXTAREA_CLASS =
  "w-full rounded-md border border-input bg-canvas px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted-soft outline-none transition-colors duration-150 focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/15";

type ApiBlock = NonNullable<EmailTemplateConfig["blocks"]>[number];

/** The stored block shape is permissive; the write payload fills every default. */
function toApiBlock(block: TemplateBlockView): ApiBlock {
  switch (block.type) {
    case "text":
      return { type: "text", text: block.text };
    case "summary":
      return { type: "summary" };
    case "field":
      return {
        type: "field",
        field: block.field,
        show: block.show ?? "current",
        emphasis: block.emphasis ?? false,
        label: block.label ?? null,
      };
    case "list_changes":
      return { type: "list_changes", field: block.field, limit: block.limit ?? 8 };
    case "all_fields":
      return { type: "all_fields", fields: block.fields ?? null };
    case "event_time":
      return { type: "event_time" };
    case "monitor_link":
      return { type: "monitor_link" };
    case "evidence_link":
      return { type: "evidence_link" };
    case "divider":
      return { type: "divider" };
  }
}

const DEFAULT_STYLE: NonNullable<EmailTemplateConfig["style"]> = {
  page_background: "#f5f2ea",
  surface: "#fffdf8",
  text: "#1e1b16",
  muted: "#6f6759",
  accent: "#22584a",
  font: "sans",
  heading_scale: "regular",
  density: "regular",
  radius: 14,
  border: true,
  uppercase_labels: false,
};

function toApiConfig(design: EmailTemplateConfigView): EmailTemplateConfig {
  return {
    version: 1,
    style: { ...DEFAULT_STYLE, ...(design.style ?? {}) },
    subject: design.subject,
    intros: design.intros ?? {},
    blocks: (design.blocks ?? []).map(toApiBlock),
  };
}

/**
 * A design is written, not assembled: one sentence goes to the model, the
 * returned layout is shown as a real mail, and only an explicit save stores it.
 */
export function TemplateEditor({
  template,
  onClose,
}: {
  template: EmailTemplateView | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { errorText } = useFormat();
  const write = useWriteEmailTemplate();
  const generate = useGenerateEmailTemplate();
  const previewMail = usePreviewEmailTemplate();

  const stored = template ? parseTemplateConfig(template.config) : null;
  const storedConfig = stored ? toApiConfig(stored) : null;
  const [name, setName] = useState(template?.name ?? "");
  const [prompt, setPrompt] = useState(template?.description ?? "");
  const [config, setConfig] = useState<EmailTemplateConfig | null>(storedConfig);
  // null means "follow the design in hand"; typing pins the header line.
  const [subject, setSubject] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const design = config ?? storedConfig;
  const subjectValue = subject ?? design?.subject ?? "";
  const rendered = previewMail.data?.rendered_emails ?? [];

  function describeFailure(failure: unknown): string {
    if (!(failure instanceof ApiError)) return t("templates.error.generate");
    if (failure.code === "template_generation_failed") return t("templates.error.generate");
    return errorText(failure.code);
  }

  async function runGeneration() {
    if (!prompt.trim()) return;
    setError(null);
    try {
      const proposal = await generate.mutateAsync(prompt.trim());
      setConfig(proposal.config);
      setSubject(null);
      if (!name.trim()) setName(proposal.name);
      await previewMail.mutateAsync(proposal.config);
    } catch (failure) {
      setError(describeFailure(failure));
    }
  }

  async function runPreview() {
    if (!design) return;
    setError(null);
    try {
      await previewMail.mutateAsync(applySubject(design, subjectValue));
    } catch (failure) {
      setError(describeFailure(failure));
    }
  }

  async function save() {
    setError(null);
    if (!name.trim()) {
      setError(t("templates.error.nameRequired"));
      return;
    }
    if (!design) {
      setError(t("templates.error.subjectRequired"));
      return;
    }
    try {
      await write.mutateAsync({
        id: template?.id,
        body: {
          name: name.trim(),
          description: prompt.trim() || (template?.description ?? ""),
          config: applySubject(design, subjectValue),
        },
      });
      onClose();
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "template_name_conflict") {
        setError(t("templates.error.conflict"));
      } else if (failure instanceof ApiError && failure.code === "validation_failed") {
        setError(t("templates.error.save"));
      } else {
        setError(describeFailure(failure));
      }
    }
  }

  const busy = generate.isPending || previewMail.isPending || write.isPending;
  const canGenerate = prompt.trim().length > 0 && !generate.isPending;

  return (
    <Dialog
      open
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {template ? t("templates.editor.editTitle") : t("templates.editor.createTitle")}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="template-prompt">{t("templates.editor.prompt")}</Label>
            <textarea
              id="template-prompt"
              value={prompt}
              rows={3}
              maxLength={1000}
              placeholder={t("templates.editor.promptPlaceholder")}
              className={TEXTAREA_CLASS}
              onChange={(event) => setPrompt(event.target.value)}
            />
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Button
                type="button"
                size="sm"
                disabled={!canGenerate}
                onClick={() => void runGeneration()}
              >
                <Sparkles strokeWidth={1.5} />
                {generate.isPending
                  ? t("templates.editor.generating")
                  : config
                    ? t("templates.editor.regenerate")
                    : t("templates.editor.generate")}
              </Button>
              {design && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={previewMail.isPending}
                  onClick={() => void runPreview()}
                >
                  {previewMail.isPending
                    ? t("templates.editor.previewing")
                    : t("templates.action.preview")}
                </Button>
              )}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="template-name">{t("templates.editor.name")}</Label>
              <Input
                id="template-name"
                value={name}
                maxLength={200}
                placeholder={t("templates.editor.namePlaceholder")}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="template-subject">{t("templates.editor.subject")}</Label>
              <Input
                id="template-subject"
                value={subjectValue}
                maxLength={200}
                disabled={!design}
                onChange={(event) => setSubject(event.target.value)}
              />
            </div>
          </div>
          <p className="meta">{t("templates.editor.subjectHint")}</p>

          {rendered.length > 0 && <EmailPreview emails={rendered} />}
          {previewMail.isPending && <p className="meta">{t("templates.editor.previewing")}</p>}

          {error && (
            <p role="alert" className="text-[13px] text-error">
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-hairline pt-4">
            <p className="meta max-w-sm">{t("templates.editor.proposalHint")}</p>
            <div className="flex shrink-0 gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={onClose}>
                {t("common.close")}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={busy || !design}
                onClick={() => void save()}
              >
                {write.isPending ? t("templates.editor.saving") : t("templates.editor.save")}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function applySubject(design: EmailTemplateConfig, subject: string): EmailTemplateConfig {
  const trimmed = subject.trim();
  return trimmed && trimmed !== design.subject ? { ...design, subject: trimmed } : design;
}

function EmailPreview({ emails }: { emails: RenderedEmailView[] }) {
  const { t } = useI18n();
  const { eventLabel } = useFormat();
  const [selectedType, setSelectedType] = useState<string | null>(null);
  if (emails.length === 0) return null;
  const selected = emails.find((email) => email.event_type === selectedType) ?? emails[0];
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {emails.map((email) => (
          <Button
            key={email.event_type}
            type="button"
            size="sm"
            variant={email.event_type === selected.event_type ? "secondary" : "ghost"}
            className="h-7 px-2 text-[13px]"
            onClick={() => setSelectedType(email.event_type)}
          >
            {eventLabel(email.event_type)}
          </Button>
        ))}
      </div>
      <p className="num truncate text-[13px] text-muted-soft">{selected.subject}</p>
      <iframe
        sandbox=""
        title={t("templates.editor.previewTitle")}
        srcDoc={selected.preview_html ?? selected.html}
        className="h-72 w-full rounded-lg border bg-white"
      />
    </div>
  );
}

export function TemplatePreviewDialog({
  template,
  onClose,
}: {
  template: EmailTemplateView;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const preview = usePreviewEmailTemplate();
  const { mutateAsync } = preview;
  const config = useMemo(() => {
    const design = parseTemplateConfig(template.config);
    return design ? toApiConfig(design) : null;
  }, [template]);

  return (
    <Dialog
      open
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("templates.editor.previewTitle")}</DialogTitle>
        </DialogHeader>
        <p className="t-body-sm mb-3 text-muted-foreground">{t("templates.editor.previewBody")}</p>
        {!config && (
          <p role="alert" className="text-[13px] text-error">
            {t("templates.error.preview")}
          </p>
        )}
        {config && preview.isIdle && (
          <Button size="sm" onClick={() => void mutateAsync(config)}>
            {t("templates.action.preview")}
          </Button>
        )}
        {config && preview.isPending && <p className="meta">{t("templates.editor.previewing")}</p>}
        {config && preview.isError && (
          <p role="alert" className="text-[13px] text-error">
            {t("templates.error.preview")}
          </p>
        )}
        {preview.data && <EmailPreview emails={preview.data.rendered_emails} />}
      </DialogContent>
    </Dialog>
  );
}
