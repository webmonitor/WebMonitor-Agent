"use client";

import { useMemo } from "react";
import { useI18n } from "@/lib/i18n";
import type { Locale, MessageKey } from "@/lib/i18n/messages";
import { ApiError } from "@/lib/api/client";

function toDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function sameDay(left: Date, right: Date): boolean {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate();
}


const STATUS_KEYS: Partial<Record<string, MessageKey>> = {
  queued: "format.status.queued",
  running: "format.status.running",
  succeeded: "format.status.succeeded",
  failed: "format.status.failed",
  cancelled: "format.status.cancelled",
  discarded: "format.status.discarded",
  active: "format.status.active",
  paused: "format.status.paused",
  draft: "format.status.draft",
  published: "format.status.published",
  healthy: "format.status.healthy",
  pending_first_success: "format.status.pending_first_success",
  ready: "format.status.ready",
  sent: "format.status.sent",
  sending: "format.status.sending",
  retrying: "format.status.retrying",
  started: "format.status.started",
};

const EVENT_KEYS: Partial<Record<string, MessageKey>> = {
  list_changed: "format.event.list_changed",
  content_changed: "format.event.content_changed",
  run_failed: "format.event.run_failed",
  recovered: "format.event.recovered",
};

const STEP_KEYS: Partial<Record<string, MessageKey>> = {
  analyze_target: "format.step.analyze_target",
  probe_target: "format.step.probe_target",
  capture_network: "format.step.capture_network",
  replay_request: "format.step.replay_request",
  save_monitor_draft: "format.step.save_monitor_draft",
  preview_monitor: "format.step.preview_monitor",
  request_creation: "format.step.request_creation",
};

const ERROR_KEYS: Partial<Record<string, MessageKey>> = {
  monitor_not_active: "format.error.monitor_not_active",
  preview_not_ready: "format.error.preview_not_ready",
  collection_invalid: "format.error.collection_invalid",
  collection_failed: "format.error.collection_failed",
  notification_routes_invalid: "format.error.notification_routes_invalid",
  template_not_found: "format.error.template_not_found",
  template_unavailable: "format.error.template_unavailable",
  template_incompatible: "format.error.template_incompatible",
  template_name_conflict: "format.error.template_name_conflict",
  settings_incomplete: "format.error.settings_incomplete",
  url_forbidden: "format.error.url_forbidden",
  target_unavailable: "format.error.target_unavailable",
  target_http_error: "format.error.target_http_error",
  collection_timeout: "format.error.collection_timeout",
  browser_unavailable: "format.error.browser_unavailable",
  storage_unavailable: "format.error.storage_unavailable",
  template_contract_failed: "format.error.template_contract_failed",
  model_unavailable: "format.error.model_unavailable",
  model_output_invalid: "format.error.model_output_invalid",
  run_timeout: "format.error.run_timeout",
  max_turns_exceeded: "format.error.max_turns_exceeded",
  run_budget_exhausted: "format.error.run_budget_exhausted",
  run_failed: "format.error.run_failed",
  job_timeout: "format.error.job_timeout",
  lease_expired: "format.error.lease_expired",
  preview_missing: "format.error.preview_missing",
  preview_expired: "format.error.preview_expired",
  preview_stale: "format.error.preview_stale",
  stale_revision: "format.error.stale_revision",
  run_in_progress: "format.error.run_in_progress",
  draft_not_editable: "format.error.draft_not_editable",
  notification_recipients_empty: "format.error.notification_recipients_empty",
  account_exists: "format.error.account_exists",
  administrator_required: "format.error.administrator_required",
  cannot_disable_self: "format.error.cannot_disable_self",
  collection_limit: "format.error.collection_limit",
  conversation_empty: "format.error.conversation_empty",
  csrf_invalid: "format.error.csrf_invalid",
  database_unavailable: "format.error.database_unavailable",
  delivery_aborted: "format.error.delivery_aborted",
  delivery_attempts_exhausted: "format.error.delivery_attempts_exhausted",
  draft_empty: "format.error.draft_empty",
  draft_missing: "format.error.draft_missing",
  email_not_allowed: "format.error.email_not_allowed",
  execution_superseded: "format.error.execution_superseded",
  group_in_use: "format.error.group_in_use",
  group_name_conflict: "format.error.group_name_conflict",
  http_analysis_required: "format.error.http_analysis_required",
  idempotency_conflict: "format.error.idempotency_conflict",
  internal_error: "format.error.internal_error",
  invalid_email: "format.error.invalid_email",
  invalid_invitation_ttl: "format.error.invalid_invitation_ttl",
  invalid_password: "format.error.invalid_password",
  job_conflict: "format.error.job_conflict",
  message_empty: "format.error.message_empty",
  message_too_long: "format.error.message_too_long",
  monitor_archived: "format.error.monitor_archived",
  not_found: "format.error.not_found",
  not_ready: "format.error.not_ready",
  origin_invalid: "format.error.origin_invalid",
  quota_exceeded: "format.error.quota_exceeded",
  request_too_large: "format.error.request_too_large",
  run_cancelled: "format.error.run_cancelled",
  run_not_active: "format.error.run_not_active",
  smtp_configuration_error: "format.error.smtp_configuration_error",
  smtp_network_error: "format.error.smtp_network_error",
  smtp_protocol_error: "format.error.smtp_protocol_error",
  smtp_recipient_refused: "format.error.smtp_recipient_refused",
  smtp_rejected: "format.error.smtp_rejected",
  smtp_tls_failed: "format.error.smtp_tls_failed",
  template_generation_failed: "format.error.template_generation_failed",
  unsupported_content_encoding: "format.error.unsupported_content_encoding",
  worker_unavailable: "format.error.worker_unavailable",
  forbidden: "format.error.forbidden",
  unauthenticated: "format.error.unauthenticated",
  rate_limited: "format.error.rate_limited",
  invalid_credentials: "format.error.invalid_credentials",
  validation_failed: "format.error.validation_failed",
  csrf_unavailable: "format.error.csrf_unavailable",
  network_unavailable: "format.error.network_unavailable",
  request_failed: "format.error.request_failed",
  registration_failed: "format.error.registration_failed",
  api_assertion_failed: "format.error.api_assertion_failed",
  api_schema_invalid: "format.error.api_schema_invalid",
  api_empty_result: "format.error.api_empty_result",
  api_template_unresolved: "format.error.api_template_unresolved",
  api_pagination_limit: "format.error.api_pagination_limit",
};

const WARNING_KEYS: Partial<Record<string, MessageKey>> = {
  pagination_coverage_unproven: "format.warning.pagination_coverage_unproven",
  coverage_bounded: "format.warning.coverage_bounded",
  deletion_coverage_bounded: "format.warning.deletion_coverage_bounded",
  template_contract_failed: "format.warning.template_contract_failed",
  pagination_truncated: "format.warning.pagination_truncated",
};

const OPERATOR_KEYS: Partial<Record<string, MessageKey>> = {
  increase_gte: "format.operator.increase_gte",
  decrease_gte: "format.operator.decrease_gte",
  change_gte: "format.operator.change_gte",
  gt: "format.operator.gt",
  gte: "format.operator.gte",
  lt: "format.operator.lt",
  lte: "format.operator.lte",
  eq: "format.operator.eq",
};

type Rule = {
  type?: string;
  field?: string;
  operator?: string;
  value?: number | string;
  keyword?: string;
  watch_fields?: string[];
};

const ARRAY_JOIN: Record<Locale, string> = { en: ", ", "zh-CN": "、" };
const ENTRY_JOIN: Record<Locale, string> = { en: "; ", "zh-CN": "，" };
const ENTRY_SEPARATOR: Record<Locale, string> = { en: ": ", "zh-CN": "：" };
const LIST_JOIN: Record<Locale, string> = { en: ", ", "zh-CN": "、" };

export function useFormat() {
  const { locale, t } = useI18n();

  return useMemo(() => {
    const intl = locale === "zh-CN" ? "zh-CN" : "en-US";
    const dateTime = new Intl.DateTimeFormat(intl, {
      month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    });
    const dateTimeYear = new Intl.DateTimeFormat(intl, {
      year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    });
    const monthDay = new Intl.DateTimeFormat(intl, { month: "long", day: "numeric" });
    const monthDayYear = new Intl.DateTimeFormat(intl, { year: "numeric", month: "long", day: "numeric" });
    const fullDateTime = new Intl.DateTimeFormat(intl, {
      year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    });
    const valueDate = new Intl.DateTimeFormat(intl, {
      year: "numeric", month: locale === "zh-CN" ? "long" : "short", day: "numeric",
    });
    const clock = new Intl.DateTimeFormat(intl, {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
    const numbers = new Intl.NumberFormat(intl);

    /** "Today 11:00" / "Yesterday 21:40" / "10/27 09:12" — compact, used in lists. */
    function formatTime(value?: string | null): string {
      const date = toDate(value);
      if (!date) return "—";
      const now = new Date();
      const time = clock.format(date).slice(0, 5);
      if (sameDay(date, now)) return `${t("format.today")} ${time}`;
      const yesterday = new Date(now);
      yesterday.setDate(now.getDate() - 1);
      if (sameDay(date, yesterday)) return `${t("format.yesterday")} ${time}`;
      // A different year is the one thing a month/day pair cannot convey.
      return (date.getFullYear() === now.getFullYear() ? dateTime : dateTimeYear).format(date);
    }

    function formatClock(value?: string | null): string {
      const date = toDate(value);
      return date ? clock.format(date) : "—";
    }

    function formatDateTime(value?: string | null): string {
      const date = toDate(value);
      return date ? fullDateTime.format(date) : "—";
    }

    function formatRelative(value?: string | null): string {
      const date = toDate(value);
      if (!date) return "—";
      const seconds = Math.round((date.getTime() - Date.now()) / 1000);
      const magnitude = Math.abs(seconds);
      const [amount, unit]: [number, string] = magnitude < 60
        ? [Math.max(magnitude, 1), locale === "zh-CN" ? "秒" : "second"]
        : magnitude < 3600
          ? [Math.round(magnitude / 60), locale === "zh-CN" ? "分钟" : "minute"]
          : magnitude < 86400
            ? [Math.round(magnitude / 3600), locale === "zh-CN" ? "小时" : "hour"]
            : [Math.round(magnitude / 86400), locale === "zh-CN" ? "天" : "day"];
      const plural = amount === 1 ? unit : `${unit}s`;
      return locale === "zh-CN"
        ? seconds > 0 ? `${amount} ${unit}后` : `${amount} ${unit}前`
        : seconds > 0
          ? `in ${amount} ${plural}`
          : `${amount} ${plural} ago`;
    }

    function dayLabel(value?: string | null): string {
      const date = toDate(value);
      if (!date) return t("format.unknownTime");
      const now = new Date();
      if (sameDay(date, now)) return t("format.today");
      const yesterday = new Date(now);
      yesterday.setDate(now.getDate() - 1);
      if (sameDay(date, yesterday)) return t("format.yesterday");
      return (date.getFullYear() === now.getFullYear() ? monthDay : monthDayYear).format(date);
    }

    function money(value: Record<string, unknown>): string | null {
      const amount = value.amount;
      if (typeof amount !== "string" && typeof amount !== "number") return null;
      const currency = typeof value.currency === "string" ? value.currency : "";
      // The ISO code is the whole contract; no currency is rendered specially.
      return currency ? `${currency} ${amount}` : String(amount);
    }

    function formatValue(value: unknown, type?: string): string {
      if (value === null || value === undefined || value === "") return "—";
      if (typeof value === "boolean") return value ? t("format.yes") : t("format.no");
      if (typeof value === "number") return numbers.format(value);
      if (typeof value === "string") {
        // Only a declared date field drops its time: the type is the contract.
        if (type === "date") {
          const date = toDate(value);
          return date ? valueDate.format(date) : value;
        }
        const date = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value) ? toDate(value) : null;
        return date ? fullDateTime.format(date) : value;
      }
      if (Array.isArray(value)) {
        if (value.length === 0) return t("format.empty");
        return value.map((item) => formatValue(item)).join(ARRAY_JOIN[locale]);
      }
      if (typeof value === "object") {
        const record = value as Record<string, unknown>;
        const asMoney = money(record);
        if (asMoney) return asMoney;
        const entries = Object.entries(record);
        if (entries.length === 0) return "—";
        return entries
          .map(([key, item]) => `${key}${ENTRY_SEPARATOR[locale]}${formatValue(item)}`)
          .join(ENTRY_JOIN[locale]);
      }
      return String(value);
    }

    function statusLabel(status?: string | null): string {
      if (!status) return "—";
      const key = STATUS_KEYS[status];
      return key ? t(key) : status;
    }

    function eventLabel(type?: string | null): string {
      if (!type) return t("format.change");
      const key = EVENT_KEYS[type];
      return key ? t(key) : type;
    }

    function stepLabel(name: string): string {
      const key = STEP_KEYS[name];
      return key ? t(key) : name;
    }

    function errorText(failure?: string | Error | null): string {
      const code = failure instanceof ApiError ? failure.code : typeof failure === "string" ? failure : undefined;
      if (!code) return failure ? t("format.operationFailed") : t("format.unknownReason");
      const key = ERROR_KEYS[code];
      return key ? t(key) : t("format.operationFailed");
    }

    function warningText(warning: string): string {
      const [code, target] = warning.split(":");
      const key = WARNING_KEYS[code];
      const label = key ? t(key) : code.replace(/_/g, " ");
      return target ? `${label} (${eventLabel(target)})` : label;
    }

    /** A tool step's own elapsed time: "0.4s", "12s", "1m 12s". */
    function formatDuration(ms?: number | null): string {
      if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return "—";
      const seconds = ms / 1000;
      if (seconds < 10) return `${seconds.toFixed(1)}s`;
      if (seconds < 60) return `${Math.round(seconds)}s`;
      const minutes = Math.floor(seconds / 60);
      return `${minutes}m ${Math.round(seconds - minutes * 60)}s`;
    }

    /** Token totals stay readable in a quiet meta line: 812, 6.4k, 128k. */
    function formatTokens(count?: number | null): string {
      if (!count || !Number.isFinite(count)) return "—";
      if (count < 1000) return numbers.format(count);
      if (count < 100_000) return `${(count / 1000).toFixed(1)}k`;
      return `${Math.round(count / 1000)}k`;
    }

    function formatInterval(seconds?: number | null): string {
      if (!seconds) return "—";
      const unit = (count: number, one: string, many: string, zh: string) =>
        locale === "zh-CN" ? `${count} ${zh}` : `${count} ${count === 1 ? one : many}`;
      if (seconds % 86400 === 0) return t("format.interval", { duration: unit(seconds / 86400, "day", "days", "天") });
      if (seconds % 3600 === 0) return t("format.interval", { duration: unit(seconds / 3600, "hour", "hours", "小时") });
      if (seconds % 60 === 0) return t("format.interval", { duration: unit(seconds / 60, "minute", "minutes", "分钟") });
      return t("format.interval", { duration: unit(seconds, "second", "seconds", "秒") });
    }

    function coverageLabel(scope?: string | null): string {
      if (scope === "full") return t("monitors.config.coverageFull");
      if (scope === "bounded") return t("monitors.config.coverageBounded");
      return "—";
    }

    function formatTimezone(zone?: string | null): string {
      return zone || "—";
    }

    function formatMode(mode?: string | null): string {
      return mode === "browser" ? t("format.browser") : t("format.http");
    }

    function fieldLabel(field: { name: string; semantic?: string | null }): string {
      const semantic = (field.semantic ?? "").trim();
      const head = semantic.split(/[，,。；;（(：:、\n]/)[0]?.trim() ?? "";
      if (head && head.length <= 14) return head;
      if (head) return `${head.slice(0, 12)}…`;
      return field.name;
    }

    function fieldLabels(
      fields: { name: string; semantic?: string | null; item_fields?: unknown }[],
    ): Record<string, string> {
      const labels: Record<string, string> = {};
      const collect = (items: { name: string; semantic?: string | null; item_fields?: unknown }[]) => {
        for (const field of items) {
          labels[field.name] ??= fieldLabel(field);
          if (Array.isArray(field.item_fields)) {
            collect(field.item_fields as { name: string; semantic?: string | null; item_fields?: unknown }[]);
          }
        }
      };
      collect(fields);
      return labels;
    }

    function describeRule(rule: Rule, labels: Record<string, string> = {}): string {
      const field = (rule.field && labels[rule.field]) || rule.field || t("format.field");
      const value = rule.value ?? "";
      const operatorKey = rule.operator ? OPERATOR_KEYS[rule.operator] : undefined;
      const operator = operatorKey
        ? t(operatorKey)
        : t("format.change");
      switch (rule.type) {
        case "number_percent_change":
          return t("format.rule.percent", { field, operator, value });
        case "number_absolute_change":
          return t("format.rule.absolute", { field, operator, value });
        case "threshold":
          return t("format.rule.threshold", {
            field,
            operator: operatorKey ? operator : t("format.reached"),
            value,
          });
        case "text_changed":
          return t("format.rule.text", { field });
        case "keyword_present":
          return t("format.rule.keywordPresent", { keyword: rule.keyword ?? "" });
        case "keyword_absent":
          return t("format.rule.keywordAbsent", { keyword: rule.keyword ?? "" });
        case "list_added":
          return t("format.rule.added", { field });
        case "list_removed":
          return t("format.rule.removed", { field });
        case "list_updated":
          return t("format.rule.updated", {
            field,
            fields: (rule.watch_fields ?? []).join(LIST_JOIN[locale]),
          });
        default:
          return t("format.rule.changed", { field });
      }
    }

    function describeRules(rules: Rule[], mode?: string, labels: Record<string, string> = {}): string {
      if (rules.length === 0) return t("format.rule.default");
      return rules
        .map((rule) => describeRule(rule, labels))
        .join(t(mode === "all" ? "format.rule.and" : "format.rule.or"));
    }

    return {
      formatTime,
      formatClock,
      formatDateTime,
      formatRelative,
      dayLabel,
      formatValue,
      statusLabel,
      eventLabel,
      stepLabel,
      errorText,
      warningText,
      formatDuration,
      formatTokens,
      formatInterval,
      formatTimezone,
      coverageLabel,
      formatMode,
      fieldLabel,
      fieldLabels,
      describeRule,
      describeRules,
    };
  }, [locale, t]);
}

export function formatJson(value: unknown): string {
  if (value === null || value === undefined) return "—";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 KB";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
