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

const CURRENCY_SYMBOLS: Record<string, string> = { CNY: "¥", USD: "$", EUR: "€", GBP: "£", JPY: "¥" };

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
  price_changed: "format.event.price_changed",
  list_changed: "format.event.list_changed",
  content_changed: "format.event.content_changed",
  run_failed: "format.event.run_failed",
  recovered: "format.event.recovered",
};

const STEP_KEYS: Partial<Record<string, MessageKey>> = {
  analyze_target: "format.step.analyze_target",
  list_notification_groups: "format.step.list_notification_groups",
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
  url_forbidden: "format.error.url_forbidden",
  target_unavailable: "format.error.target_unavailable",
  target_http_error: "format.error.target_http_error",
  collection_timeout: "format.error.collection_timeout",
  browser_unavailable: "format.error.browser_unavailable",
  storage_unavailable: "format.error.storage_unavailable",
  template_contract_failed: "format.error.template_contract_failed",
  model_unavailable: "format.error.model_unavailable",
  lease_expired: "format.error.lease_expired",
  preview_missing: "format.error.preview_missing",
  preview_expired: "format.error.preview_expired",
  preview_stale: "format.error.preview_stale",
  stale_revision: "format.error.stale_revision",
  run_in_progress: "format.error.run_in_progress",
  notification_recipients_empty: "format.error.notification_recipients_empty",
  notification_group_unavailable: "format.error.notification_group_unavailable",
  forbidden: "format.error.forbidden",
  unauthenticated: "format.error.unauthenticated",
  rate_limited: "format.error.rate_limited",
  invalid_credentials: "format.error.invalid_credentials",
  validation_failed: "format.error.validation_failed",
  csrf_unavailable: "format.error.csrf_unavailable",
  network_unavailable: "format.error.network_unavailable",
  request_failed: "format.error.request_failed",
  registration_failed: "format.error.registration_failed",
};

const WARNING_KEYS: Partial<Record<string, MessageKey>> = {
  pagination_coverage_unproven: "format.warning.pagination_coverage_unproven",
  coverage_bounded: "format.warning.coverage_bounded",
  template_contract_failed: "format.warning.template_contract_failed",
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

const FIELD_KEYS: Partial<Record<string, MessageKey>> = {
  current_price: "format.field.current_price",
  previous_price: "format.field.previous_price",
  price: "format.field.price",
  current_fee: "format.field.current_fee",
  effective_date: "format.field.effective_date",
  title: "format.field.title",
  name: "format.field.name",
  stock: "format.field.stock",
  quantity: "format.field.quantity",
  status: "format.field.status",
  summary: "format.field.summary",
  content: "format.field.content",
  date: "format.field.date",
  time: "format.field.time",
};

const ZONE_KEYS: Partial<Record<string, MessageKey>> = {
  "Asia/Shanghai": "format.zone.Asia/Shanghai",
  "Asia/Tokyo": "format.zone.Asia/Tokyo",
  "Europe/London": "format.zone.Europe/London",
  "America/New_York": "format.zone.America/New_York",
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
    const fullDateTime = new Intl.DateTimeFormat(intl, {
      year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
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
      return dateTime.format(date);
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
      return new Intl.DateTimeFormat(intl, { month: "long", day: "numeric" }).format(date);
    }

    function money(value: Record<string, unknown>): string | null {
      const amount = value.amount;
      if (typeof amount !== "string" && typeof amount !== "number") return null;
      const currency = typeof value.currency === "string" ? value.currency : "";
      const symbol = CURRENCY_SYMBOLS[currency];
      const text = String(amount);
      if (symbol) return `${symbol}${text}`;
      return currency ? `${currency} ${text}` : text;
    }

    function formatValue(value: unknown): string {
      if (value === null || value === undefined || value === "") return "—";
      if (typeof value === "boolean") return value ? t("format.yes") : t("format.no");
      if (typeof value === "number") return numbers.format(value);
      if (typeof value === "string") {
        const date = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value) ? toDate(value) : null;
        return date ? dateTime.format(date) : value;
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

    function formatInterval(seconds?: number | null): string {
      if (!seconds) return "—";
      if (seconds % 86400 === 0) return t("format.interval", { duration: locale === "zh-CN" ? `${seconds / 86400} 天` : `${seconds / 86400} days` });
      if (seconds % 3600 === 0) return t("format.interval", { duration: locale === "zh-CN" ? `${seconds / 3600} 小时` : `${seconds / 3600} hours` });
      if (seconds % 60 === 0) return t("format.interval", { duration: locale === "zh-CN" ? `${seconds / 60} 分钟` : `${seconds / 60} minutes` });
      return t("format.interval", { duration: locale === "zh-CN" ? `${seconds} 秒` : `${seconds} seconds` });
    }

    function formatTimezone(zone?: string | null): string {
      if (!zone) return "—";
      const key = ZONE_KEYS[zone];
      return key ? t(key) : zone;
    }

    function formatMode(mode?: string | null): string {
      return mode === "browser" ? t("format.browser") : t("format.http");
    }

    function fieldLabel(field: { name: string; semantic?: string | null }): string {
      const semantic = (field.semantic ?? "").trim();
      const head = semantic.split(/[，,。；;（(：:、\n]/)[0]?.trim() ?? "";
      if (head && head.length <= 14) return head;
      if (head) return `${head.slice(0, 12)}…`;
      const key = FIELD_KEYS[field.name];
      return key ? t(key) : field.name;
    }

    function fieldLabels(
      fields: { name: string; semantic?: string | null }[],
    ): Record<string, string> {
      return Object.fromEntries(fields.map((field) => [field.name, fieldLabel(field)]));
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
      formatInterval,
      formatTimezone,
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
