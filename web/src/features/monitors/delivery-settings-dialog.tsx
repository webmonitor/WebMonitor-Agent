"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, Mail, Webhook } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ListPagination } from "@/components/list-pagination";
import { Select } from "@/components/ui/select";
import {
  frozenTemplateName,
  missingGroupIds,
  withSelectedTemplate,
} from "@/features/monitors/delivery-settings-utils";
import { ApiError } from "@/lib/api/client";
import {
  useEmailTemplates,
  useGroups,
  useUpdateMonitorSettings,
  type MonitorDetail,
} from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/providers";

const PRESETS = [60, 300, 900, 3600, 21600, 86400];
const MIN_INTERVAL = 60;
const MAX_INTERVAL = 86400;
const MAX_COOLDOWN = 2_147_483_647;
const CLOCK_TIME = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

/**
 * Delivery is set by hand, on the monitor: who receives the mail, how often the
 * page is checked, and which design is used. It is deliberately outside the
 * conversation — creating a monitor never asks for any of it.
 */
export function DeliverySettingsDialog({
  monitor,
  open,
  onOpenChange,
}: {
  monitor: MonitorDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const { errorText, formatInterval } = useFormat();
  const { user } = useAuth();
  const groups = useGroups(100);
  const templates = useEmailTemplates();
  const update = useUpdateMonitorSettings();

  const storedChannel: "email" | "webhook" | "both" =
    monitor.delivery_channel === "both" ? "both" : monitor.delivery_channel === "webhook" ? "webhook" : "email";
  const [channel, setChannel] = useState<"email" | "webhook" | "both">(storedChannel);
  const storedFailure = monitor.event_channels?.run_failed;
  const storedFailureChannel = storedFailure === "email" || storedFailure === "webhook"
    ? storedFailure : "";
  const [failureChannel, setFailureChannel] = useState<"" | "email" | "webhook">(storedFailureChannel);
  const [selectedGroups, setSelectedGroups] = useState<string[]>(monitor.notification_group_ids);
  const [webhookUrl, setWebhookUrl] = useState(monitor.webhook_url ?? "");
  const [interval, setInterval] = useState<number | null>(monitor.interval_seconds);
  const [timezone, setTimezone] = useState(monitor.timezone);
  const storedTemplate = monitor.email_template_id ?? null;
  const [templateId, setTemplateId] = useState<string | null>(storedTemplate);
  const storedCooldown = monitor.notification_cooldown_seconds ?? 0;
  const storedQuietEnabled = monitor.quiet_hours != null;
  const storedQuietStart = monitor.quiet_hours?.start ?? "22:00";
  const storedQuietEnd = monitor.quiet_hours?.end ?? "07:00";
  const [cooldown, setCooldown] = useState<number | null>(storedCooldown);
  const [quietEnabled, setQuietEnabled] = useState(storedQuietEnabled);
  const [quietStart, setQuietStart] = useState(storedQuietStart);
  const [quietEnd, setQuietEnd] = useState(storedQuietEnd);
  const [error, setError] = useState<string | null>(null);

  // Every open starts from the monitor as stored, so a cancelled edit leaves nothing.
  useEffect(() => {
    if (!open) return;
    setChannel(storedChannel);
    setFailureChannel(storedFailureChannel);
    setSelectedGroups(monitor.notification_group_ids);
    setWebhookUrl(monitor.webhook_url ?? "");
    setInterval(monitor.interval_seconds);
    setTimezone(monitor.timezone);
    setTemplateId(storedTemplate);
    setCooldown(storedCooldown);
    setQuietEnabled(storedQuietEnabled);
    setQuietStart(storedQuietStart);
    setQuietEnd(storedQuietEnd);
    setError(null);
  }, [open, storedChannel, monitor.notification_group_ids, monitor.webhook_url,
      monitor.interval_seconds, monitor.timezone, storedTemplate, storedCooldown,
      storedQuietEnabled, storedQuietStart, storedQuietEnd, storedFailureChannel]);

  const dirty =
    channel !== storedChannel ||
    failureChannel !== storedFailureChannel ||
    [...selectedGroups].sort().join() !== [...monitor.notification_group_ids].sort().join() ||
    webhookUrl.trim() !== (monitor.webhook_url ?? "") ||
    interval !== monitor.interval_seconds ||
    timezone.trim() !== monitor.timezone ||
    templateId !== storedTemplate ||
    cooldown !== storedCooldown ||
    quietEnabled !== storedQuietEnabled ||
    (quietEnabled && (quietStart !== storedQuietStart || quietEnd !== storedQuietEnd));
  const intervalValid =
    interval !== null && Number.isInteger(interval) &&
    interval >= MIN_INTERVAL && interval <= MAX_INTERVAL;
  const timezoneValid = timezone.trim().length > 0;
  const routeValid =
    (channel === "email" || webhookUrl.trim().length > 0) &&
    (channel === "webhook" || selectedGroups.length > 0);
  const cooldownValid = cooldown !== null && Number.isInteger(cooldown) &&
    cooldown >= 0 && cooldown <= MAX_COOLDOWN;
  const quietValid = !quietEnabled || (
    CLOCK_TIME.test(quietStart) && CLOCK_TIME.test(quietEnd) && quietStart !== quietEnd
  );
  const incomplete = !routeValid || !intervalValid || !cooldownValid || !quietValid;

  function toggleGroup(id: string) {
    setSelectedGroups((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  async function save() {
    setError(null);
    if (!intervalValid || !timezoneValid || !routeValid || !cooldownValid || !quietValid) return;
    try {
      await update.mutateAsync({
        monitorId: monitor.id,
        settings: {
          channel,
          event_channels: failureChannel ? { run_failed: failureChannel } : {},
          notification_group_ids: selectedGroups,
          webhook_url: webhookUrl.trim() || null,
          schedule: { interval_seconds: interval, timezone: timezone.trim() },
          email_template_id: templateId,
          notification_cooldown_seconds: cooldown,
          quiet_hours: quietEnabled ? { start: quietStart, end: quietEnd } : null,
        },
      });
      onOpenChange(false);
    } catch (failure) {
      setError(failure instanceof ApiError ? errorText(failure.code) : t("common.listError"));
    }
  }

  const groupItems = groups.data?.items ?? [];
  const missing = missingGroupIds(
    selectedGroups,
    groupItems.map((group) => group.id),
    groups.hasNextPage,
  );
  const templateItems = templates.data?.items ?? [];
  const selectedTemplateName = templateId === storedTemplate
    ? frozenTemplateName(monitor.email_template)
    : null;
  const templateOptions = withSelectedTemplate(
    [
      { value: "", label: t("templates.systemDefault") },
      ...templateItems.map((template) => ({ value: template.id, label: template.name })),
    ],
    templateId,
    selectedTemplateName,
    t("settings.template.selectedFallback", { id: templateId ?? "" }),
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="pr-6">{t("settings.dialog.title")}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          <div className="space-y-2">
            <h3 className="label-line">{t("settings.channel.title")}</h3>
            <div className="flex gap-1.5">
              <Button
                type="button"
                size="sm"
                variant={channel === "email" ? "secondary" : "outline"}
                onClick={() => setChannel("email")}
              >
                <Mail strokeWidth={1.5} />
                {t("settings.channel.email")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant={channel === "webhook" ? "secondary" : "outline"}
                onClick={() => setChannel("webhook")}
              >
                <Webhook strokeWidth={1.5} />
                {t("settings.channel.webhook")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant={channel === "both" ? "secondary" : "outline"}
                onClick={() => setChannel("both")}
              >
                <Bell strokeWidth={1.5} />
                {t("settings.channel.both")}
              </Button>
            </div>
            <p className="meta">
              {channel === "both"
                ? t("settings.channel.bothBody")
                : channel === "webhook"
                  ? t("settings.channel.webhookBody")
                  : t("settings.channel.emailBody")}
            </p>
          </div>

          {channel === "both" && (
            <div className="space-y-1.5">
              <Label htmlFor="failure-channel">{t("settings.routing.failure")}</Label>
              <select
                id="failure-channel"
                className="flex h-9 w-full rounded-md border border-input bg-canvas px-3 text-sm"
                value={failureChannel}
                onChange={(event) => setFailureChannel(event.target.value as "" | "email" | "webhook")}
              >
                <option value="">{t("settings.routing.default")}</option>
                <option value="email">{t("settings.routing.email")}</option>
                <option value="webhook">{t("settings.routing.webhook")}</option>
              </select>
              <p className="meta">{t("settings.routing.hint")}</p>
            </div>
          )}

          {channel !== "webhook" && (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="label-line flex items-center gap-1.5">
                <Bell className="size-3.5" strokeWidth={1.5} />
                {t("settings.groups.title")}
              </h3>
              {user?.role === "admin" && (
                <Link
                  href="/app/notifications"
                  className="text-[12px] text-primary-active underline-offset-2 hover:underline"
                >
                  {t("settings.groups.manage")}
                </Link>
              )}
            </div>
            {groups.isPending ? (
              <p className="meta">{t("common.loading")}</p>
            ) : groupItems.length === 0 && selectedGroups.length === 0 ? (
              <p className="meta">{t("settings.groups.empty")}</p>
            ) : (
              <ul className="space-y-1.5">
                {missing.map((id) => (
                  <li key={id} className="flex items-start gap-2 text-[14px]">
                    <span className="min-w-0 flex-1">
                      <span className="block text-warning-ink">{t("settings.groups.missing")}</span>
                      <span className="num block truncate text-[13px] text-muted-soft">{id}</span>
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7 shrink-0 px-2 text-[13px] text-muted-soft hover:text-ink"
                      onClick={() => toggleGroup(id)}
                    >
                      {t("settings.groups.remove")}
                    </Button>
                  </li>
                ))}
                {groupItems.map((group) => {
                  const checked = selectedGroups.includes(group.id);
                  return (
                    <li key={group.id}>
                      <label className="flex items-start gap-2 text-[14px]">
                        <input
                          type="checkbox"
                          className="mt-1 size-3.5 accent-[var(--primary)]"
                          checked={checked}
                          disabled={!group.enabled && !checked}
                          onChange={() => toggleGroup(group.id)}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">{group.name}</span>
                          <span className="num block text-[13px] text-muted-soft">
                            {t("activity.groups.activeCount", { count: group.member_count })}
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}
            <ListPagination query={groups} />
            {selectedGroups.length === 0 && (
              <p className="text-[13px] text-warning-ink">{t("settings.groups.required")}</p>
            )}
          </div>
          )}

          {channel !== "email" && (
          <div className="space-y-2">
            <h3 className="label-line flex items-center gap-1.5">
              <Webhook className="size-3.5" strokeWidth={1.5} />
              {t("settings.webhook.title")}
            </h3>
            <Label htmlFor="monitor-webhook" className="text-[13px] text-muted-soft">
              {t("settings.webhook.url")}
            </Label>
            <Input
              id="monitor-webhook"
              type="url"
              inputMode="url"
              value={webhookUrl}
              onChange={(event) => setWebhookUrl(event.target.value)}
              placeholder="https://hooks.example.com/services/..."
            />
            <p className="meta">{t("settings.webhook.hint")}</p>
            {webhookUrl.trim().length === 0 && (
              <p className="text-[13px] text-warning-ink">{t("settings.webhook.required")}</p>
            )}
          </div>
          )}

          <div className="space-y-2">
            <h3 className="label-line">{t("settings.schedule.title")}</h3>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((preset) => (
                <Button
                  key={preset}
                  type="button"
                  size="sm"
                  variant={interval === preset ? "secondary" : "outline"}
                  onClick={() => setInterval(preset)}
                >
                  {formatInterval(preset)}
                </Button>
              ))}
            </div>
            <Label htmlFor="monitor-interval" className="block pt-1 text-[13px] text-muted-soft">
              {t("settings.schedule.custom")}
            </Label>
            <Input
              id="monitor-interval"
              type="number"
              min={MIN_INTERVAL}
              max={MAX_INTERVAL}
              step={1}
              value={interval ?? ""}
              onChange={(event) => {
                const parsed = Number.parseInt(event.target.value, 10);
                setInterval(Number.isFinite(parsed) ? parsed : null);
              }}
            />
            <p className="meta">{t("settings.schedule.seconds")}</p>
            {!intervalValid && (
              <p className="text-[13px] text-warning-ink">{t("settings.schedule.required")}</p>
            )}
            <Label htmlFor="monitor-timezone" className="block pt-1 text-[13px] text-muted-soft">
              {t("settings.schedule.timezone")}
            </Label>
            <Input
              id="monitor-timezone"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              placeholder="Asia/Shanghai"
            />
          </div>

          <div className="space-y-3">
            <h3 className="label-line">{t("settings.noise.title")}</h3>
            <div className="space-y-2">
              <Label htmlFor="monitor-cooldown" className="text-[13px] text-muted-soft">
                {t("settings.noise.cooldown")}
              </Label>
              <Input
                id="monitor-cooldown"
                type="number"
                min={0}
                max={MAX_COOLDOWN}
                step={1}
                value={cooldown ?? ""}
                onChange={(event) => {
                  const parsed = event.target.valueAsNumber;
                  setCooldown(Number.isFinite(parsed) ? parsed : null);
                }}
              />
              <p className="meta">{t("settings.noise.cooldownHint")}</p>
              {!cooldownValid && (
                <p className="text-[13px] text-warning-ink">{t("settings.noise.cooldownRequired")}</p>
              )}
            </div>
            <label className="flex items-center gap-2 text-[14px]">
              <input
                type="checkbox"
                className="size-3.5 accent-[var(--primary)]"
                checked={quietEnabled}
                onChange={(event) => setQuietEnabled(event.target.checked)}
              />
              {t("settings.noise.quietEnabled")}
            </label>
            {quietEnabled && (
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="monitor-quiet-start" className="text-[13px] text-muted-soft">
                      {t("settings.noise.quietStart")}
                    </Label>
                    <Input
                      id="monitor-quiet-start"
                      type="time"
                      value={quietStart}
                      onChange={(event) => setQuietStart(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="monitor-quiet-end" className="text-[13px] text-muted-soft">
                      {t("settings.noise.quietEnd")}
                    </Label>
                    <Input
                      id="monitor-quiet-end"
                      type="time"
                      value={quietEnd}
                      onChange={(event) => setQuietEnd(event.target.value)}
                    />
                  </div>
                </div>
                <p className="meta">{t("settings.noise.quietHint")}</p>
                {!quietValid && (
                  <p className="text-[13px] text-warning-ink">{t("settings.noise.quietInvalid")}</p>
                )}
              </div>
            )}
          </div>

          {channel !== "webhook" && (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="label-line flex items-center gap-1.5">
                <Mail className="size-3.5" strokeWidth={1.5} />
                {t("settings.template.title")}
              </h3>
              <Link
                href="/app/templates"
                className="text-[12px] text-primary-active underline-offset-2 hover:underline"
              >
                {t("settings.template.manage")}
              </Link>
            </div>
            <Select
              label={t("settings.template.title")}
              size="md"
              value={templateId ?? ""}
              placeholder={t("templates.systemDefault")}
              onChange={(value) => setTemplateId(value || null)}
              options={templateOptions}
            />
            <ListPagination query={templates} />
            <p className="meta">{t("templates.systemDefault.body")}</p>
          </div>
          )}

          {error && (
            <p role="alert" className="text-[13px] text-error">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 border-t border-hairline pt-4">
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              {t("monitors.editor.cancel")}
            </Button>
            <Button
              size="sm"
              onClick={() => void save()}
              disabled={update.isPending || !dirty || incomplete || !timezoneValid}
            >
              {update.isPending ? t("settings.saving") : t("settings.save")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
