"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, CheckCircle2, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import {
  useEmailTemplates,
  useGroups,
  useUpdateDraft,
  type DraftView,
} from "@/lib/api/hooks";
import { parseSettings } from "@/lib/api/preview";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/providers";

const PRESETS = [60, 300, 900, 3600, 21600, 86400];
const MIN_INTERVAL = 60;
const MAX_INTERVAL = 86400;

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/**
 * The user owns who is told, how often and in which design. It renders inside the
 * approval card, so creating a monitor never leaves the conversation.
 */
export function DraftSettingsPanel({
  draft,
  onSaved,
}: {
  draft: DraftView;
  onSaved?: () => void;
}) {
  const { t } = useI18n();
  const { errorText, formatInterval } = useFormat();
  const { user } = useAuth();
  const groups = useGroups();
  const templates = useEmailTemplates();
  const update = useUpdateDraft();

  const saved = parseSettings(draft.settings);
  const savedInterval = saved?.schedule?.interval_seconds ?? null;
  const savedTimezone = saved?.schedule?.timezone || browserTimezone();
  const savedGroups = saved?.notification_group_ids ?? [];
  const savedTemplate = saved?.email_template_id ?? null;

  const [selectedGroups, setSelectedGroups] = useState<string[]>(savedGroups);
  const [interval, setInterval] = useState<number | null>(savedInterval);
  const [timezone, setTimezone] = useState<string>(savedTimezone);
  const [templateId, setTemplateId] = useState<string | null>(savedTemplate);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // A saved settings revision is the source of truth; this also clears a save banner.
  useEffect(() => {
    const current = parseSettings(draft.settings);
    setSelectedGroups(current?.notification_group_ids ?? []);
    setInterval(current?.schedule?.interval_seconds ?? null);
    setTimezone(current?.schedule?.timezone || browserTimezone());
    setTemplateId(current?.email_template_id ?? null);
    setSavedAt(null);
    setError(null);
  }, [draft.id, draft.settings_revision, draft.settings]);

  const dirty =
    [...selectedGroups].sort().join() !== [...savedGroups].sort().join() ||
    interval !== savedInterval ||
    timezone.trim() !== savedTimezone ||
    templateId !== savedTemplate;
  const intervalValid =
    interval !== null && Number.isInteger(interval) &&
    interval >= MIN_INTERVAL && interval <= MAX_INTERVAL;
  const timezoneValid = timezone.trim().length > 0;
  const incomplete = selectedGroups.length === 0 || !intervalValid;

  function toggleGroup(id: string) {
    setSavedAt(null);
    setSelectedGroups((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  async function save() {
    setError(null);
    if (!intervalValid || !timezoneValid) return;
    try {
      await update.mutateAsync({
        draftId: draft.id,
        settingsRevision: draft.settings_revision,
        settings: {
          notification_group_ids: selectedGroups,
          schedule: { interval_seconds: interval, timezone: timezone.trim() },
          email_template_id: templateId,
        },
      });
      setSavedAt(Date.now());
      onSaved?.();
    } catch (failure) {
      setError(failure instanceof ApiError ? errorText(failure.code) : t("common.listError"));
    }
  }

  const groupItems = groups.data?.items ?? [];
  const templateItems = templates.data?.items ?? [];
  const delivery = draft.delivery_preview;

  return (
    <section className="surface-pad space-y-5">
      <div className="space-y-1">
        <h2 className="text-[14px] font-medium">{t("settings.title")}</h2>
        <p className="meta leading-5">{t("settings.subtitle")}</p>
      </div>

      <div className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="label-line flex items-center gap-1.5">
            <Bell className="size-3.5" strokeWidth={1.5} />
            {t("settings.groups.title")}
          </h3>
          {user?.role === "admin" && (
            <Link
              href="/app/notifications"
              className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              {t("settings.groups.manage")}
            </Link>
          )}
        </div>
        {groups.isPending ? (
          <p className="meta">{t("common.loading")}</p>
        ) : groupItems.length === 0 ? (
          <p className="meta">{t("settings.groups.empty")}</p>
        ) : (
          <ul className="space-y-1.5">
            {groupItems.map((group) => {
              const active = group.members.filter((member) => member.active).length;
              const checked = selectedGroups.includes(group.id);
              return (
                <li key={group.id}>
                  <label className="flex items-start gap-2 text-[13px]">
                    <input
                      type="checkbox"
                      className="mt-1 size-3.5 accent-[var(--primary)]"
                      checked={checked}
                      disabled={!group.enabled}
                      onChange={() => toggleGroup(group.id)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{group.name}</span>
                      <span className="num block text-[11px] text-muted-foreground">
                        {t("settings.groups.activeMembers", { count: active })}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        {selectedGroups.length === 0 && (
          <p className="text-xs text-warning">{t("settings.groups.required")}</p>
        )}
      </div>

      <div className="space-y-2">
        <h3 className="label-line">{t("settings.schedule.title")}</h3>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((preset) => (
            <Button
              key={preset}
              type="button"
              size="sm"
              variant={interval === preset ? "default" : "outline"}
              onClick={() => {
                setSavedAt(null);
                setInterval(preset);
              }}
            >
              {formatInterval(preset)}
            </Button>
          ))}
        </div>
        <Label htmlFor="settings-interval" className="block pt-1 text-xs text-muted-foreground">
          {t("settings.schedule.custom")}
        </Label>
        <Input
          id="settings-interval"
          type="number"
          min={MIN_INTERVAL}
          max={MAX_INTERVAL}
          step={1}
          value={interval ?? ""}
          onChange={(event) => {
            setSavedAt(null);
            const parsed = Number.parseInt(event.target.value, 10);
            setInterval(Number.isFinite(parsed) ? parsed : null);
          }}
        />
        <p className="meta">{t("settings.schedule.seconds")}</p>
        {!intervalValid && (
          <p className="text-xs text-warning">{t("settings.schedule.required")}</p>
        )}
        <Label htmlFor="settings-timezone" className="block pt-1 text-xs text-muted-foreground">
          {t("settings.schedule.timezone")}
        </Label>
        <Input
          id="settings-timezone"
          value={timezone}
          onChange={(event) => {
            setSavedAt(null);
            setTimezone(event.target.value);
          }}
          placeholder="Asia/Shanghai"
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="label-line flex items-center gap-1.5">
            <Mail className="size-3.5" strokeWidth={1.5} />
            {t("settings.template.title")}
          </h3>
          <Link
            href="/app/templates"
            className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            {t("settings.template.manage")}
          </Link>
        </div>
        <select
          aria-label={t("settings.template.title")}
          className="flex h-10 w-full min-w-0 rounded-lg border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25"
          value={templateId ?? ""}
          onChange={(event) => {
            setSavedAt(null);
            setTemplateId(event.target.value || null);
          }}
        >
          <option value="">{t("templates.systemDefault")}</option>
          {templateItems.map((template) => (
            <option key={template.id} value={template.id}>
              {template.name}
            </option>
          ))}
        </select>
        <p className="meta">{t("templates.systemDefault.body")}</p>
      </div>

      <div className="space-y-2 border-t pt-3">
        <Button
          className="w-full"
          onClick={() => void save()}
          disabled={update.isPending || !dirty || incomplete || !timezoneValid}
        >
          <CheckCircle2 strokeWidth={1.5} />
          {update.isPending ? t("settings.saving") : t("settings.save")}
        </Button>
        {dirty && <p className="meta text-center">{t("settings.dirty")}</p>}
        {savedAt !== null && !dirty && (
          <p role="status" className="meta text-center text-success">
            {t("settings.saved")}
          </p>
        )}
        {!dirty && delivery ? (
          <p className="meta text-center">{t("settings.preview.ready")}</p>
        ) : (
          <p className="meta text-center">{t("settings.preview.missing")}</p>
        )}
        {error && (
          <p role="alert" className="text-xs text-error">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}
