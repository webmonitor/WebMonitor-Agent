const DATE_TIME = new Intl.DateTimeFormat("zh-CN", {
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const FULL_DATE_TIME = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

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

/** "今天 11:00" / "昨天 21:40" / "10/27 09:12" — compact, used in lists. */
export function formatTime(value?: string | null): string {
  const date = toDate(value);
  if (!date) return "—";
  const now = new Date();
  const time = DATE_TIME.format(date).replace(/^\d+\/\d+\s*/, "");
  if (sameDay(date, now)) return `今天 ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(date, yesterday)) return `昨天 ${time}`;
  return DATE_TIME.format(date);
}

/** "11:00:12" — for lists where several checks share the same minute. */
export function formatClock(value?: string | null): string {
  const date = toDate(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(date);
}

/** "2026年10月29日 11:00" — used where the exact moment matters. */
export function formatDateTime(value?: string | null): string {
  const date = toDate(value);
  return date ? FULL_DATE_TIME.format(date) : "—";
}

export function formatRelative(value?: string | null): string {
  const date = toDate(value);
  if (!date) return "—";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const future = seconds > 0;
  const magnitude = Math.abs(seconds);
  const unit = magnitude < 60
    ? [Math.max(magnitude, 1), "秒"]
    : magnitude < 3600
      ? [Math.round(magnitude / 60), "分钟"]
      : magnitude < 86400
        ? [Math.round(magnitude / 3600), "小时"]
        : [Math.round(magnitude / 86400), "天"];
  return future ? `${unit[0]} 分钟后` : `${unit[0]} ${unit[1]}前`;
}

export function dayLabel(value?: string | null): string {
  const date = toDate(value);
  if (!date) return "未知时间";
  const now = new Date();
  if (sameDay(date, now)) return "今天";
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(date, yesterday)) return "昨天";
  return new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric" }).format(date);
}

const CURRENCY_SYMBOLS: Record<string, string> = { CNY: "¥", USD: "$", EUR: "€", GBP: "£", JPY: "¥" };

function money(value: Record<string, unknown>): string | null {
  const amount = value.amount;
  if (typeof amount !== "string" && typeof amount !== "number") return null;
  const currency = typeof value.currency === "string" ? value.currency : "";
  const symbol = CURRENCY_SYMBOLS[currency];
  const text = String(amount);
  if (symbol) return `${symbol}${text}`;
  return currency ? `${currency} ${text}` : text;
}

/** Renders extracted values the way a reader expects: ¥128.50, 2026/10/31 16:00, a、b. */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return new Intl.NumberFormat("zh-CN").format(value);
  if (typeof value === "string") {
    const date = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value) ? toDate(value) : null;
    return date ? DATE_TIME.format(date) : value;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return "空";
    return value.map((item) => formatValue(item)).join("、");
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const asMoney = money(record);
    if (asMoney) return asMoney;
    const entries = Object.entries(record);
    if (entries.length === 0) return "—";
    return entries.map(([key, item]) => `${key}：${formatValue(item)}`).join("，");
  }
  return String(value);
}

const STATUS_LABELS: Record<string, string> = {
  queued: "等待中",
  running: "进行中",
  succeeded: "成功",
  failed: "失败",
  cancelled: "已取消",
  discarded: "已跳过",
  active: "监控中",
  paused: "已暂停",
  draft: "待确认",
  published: "已创建",
  healthy: "正常",
  pending_first_success: "正在建立基线",
  ready: "基线已就绪",
  sent: "已发送",
  sending: "发送中",
  retrying: "重试中",
  started: "进行中",
};

export function statusLabel(status?: string | null): string {
  if (!status) return "—";
  return STATUS_LABELS[status] ?? status;
}

const EVENT_LABELS: Record<string, string> = {
  price_changed: "价格变化",
  list_changed: "列表变化",
  content_changed: "内容变化",
  run_failed: "采集失败",
  recovered: "已恢复",
};

export function eventLabel(type?: string | null): string {
  if (!type) return "变化";
  return EVENT_LABELS[type] ?? type;
}

const STEP_LABELS: Record<string, string> = {
  analyze_target: "读取目标页面",
  list_notification_groups: "确认通知组",
  save_monitor_draft: "整理监控设置",
  preview_monitor: "试采集一次",
  request_creation: "等待你确认",
};

export function stepLabel(name: string): string {
  return STEP_LABELS[name] ?? name;
}

const ERROR_LABELS: Record<string, string> = {
  url_forbidden: "目标地址不在允许范围内",
  target_unavailable: "目标页面暂时无法访问",
  target_http_error: "目标页面返回错误",
  collection_timeout: "采集超时",
  browser_unavailable: "浏览器环境不可用",
  storage_unavailable: "证据存储暂时不可用",
  template_contract_failed: "邮件内容缺少必要字段",
  model_unavailable: "模型服务暂时不可用",
  lease_expired: "本次执行超时",
  preview_missing: "还没有预览结果",
  preview_expired: "预览已过期",
  preview_stale: "通知组或页面已变化 预览已失效",
  stale_revision: "草稿已更新",
  run_in_progress: "上一条消息还在处理",
  notification_recipients_empty: "通知组里没有可用收件人",
  notification_group_unavailable: "通知组已停用",
  forbidden: "没有权限执行该操作",
  unauthenticated: "登录已失效 请重新登录",
  rate_limited: "操作过于频繁",
  invalid_credentials: "邮箱或密码不正确",
  validation_failed: "提交的内容不符合要求",
};

export function errorText(code?: string | null): string {
  if (!code) return "未知原因";
  return ERROR_LABELS[code] ?? "操作未能完成";
}

const WARNING_LABELS: Record<string, string> = {
  pagination_coverage_unproven: "分页后的内容覆盖范围尚未确认",
  coverage_bounded: "检查范围覆盖页面的一部分",
  template_contract_failed: "邮件模板缺少必要字段，该类邮件暂不发送",
};

export function warningText(warning: string): string {
  const [code, target] = warning.split(":");
  const label = WARNING_LABELS[code] ?? code.replace(/_/g, " ");
  return target ? `${label}（${eventLabel(target)}）` : label;
}

export function formatInterval(seconds?: number | null): string {
  if (!seconds) return "—";
  if (seconds % 86400 === 0) return `每 ${seconds / 86400} 天`;
  if (seconds % 3600 === 0) return `每 ${seconds / 3600} 小时`;
  if (seconds % 60 === 0) return `每 ${seconds / 60} 分钟`;
  return `每 ${seconds} 秒`;
}

export function formatTimezone(zone?: string | null): string {
  if (!zone) return "—";
  if (zone === "Asia/Shanghai") return "北京时间";
  if (zone === "Asia/Tokyo") return "东京时间";
  if (zone === "Europe/London") return "伦敦时间";
  if (zone === "America/New_York") return "纽约时间";
  if (zone === "UTC") return "UTC";
  return zone;
}

export function formatMode(mode?: string | null): string {
  if (mode === "browser") return "浏览器渲染";
  return "直接抓取";
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

type Rule = {
  type?: string;
  field?: string;
  operator?: string;
  value?: number | string;
  keyword?: string;
  watch_fields?: string[];
};

const OPERATORS: Record<string, string> = {
  increase_gte: "上升",
  decrease_gte: "下降",
  change_gte: "变化",
  gt: "高于",
  gte: "不低于",
  lt: "低于",
  lte: "不高于",
  eq: "等于",
};

const FIELD_NAMES: Record<string, string> = {
  current_price: "当前价格",
  previous_price: "原价",
  price: "价格",
  current_fee: "当前费用",
  effective_date: "执行日期",
  title: "标题",
  name: "名称",
  stock: "库存",
  quantity: "数量",
  status: "状态",
  summary: "摘要",
  content: "内容",
  date: "日期",
  time: "时间",
};

/**
 * Field semantics written by the model are full descriptions, not labels.
 * Take the leading noun phrase and fall back to a known-name mapping.
 */
export function fieldLabel(field: { name: string; semantic?: string | null }): string {
  const semantic = (field.semantic ?? "").trim();
  const head = semantic.split(/[，,。；;（(：:、\n]/)[0]?.trim() ?? "";
  if (head && head.length <= 14) return head;
  if (head) return `${head.slice(0, 12)}…`;
  return FIELD_NAMES[field.name] ?? field.name;
}

export function fieldLabels(
  fields: { name: string; semantic?: string | null }[],
): Record<string, string> {
  return Object.fromEntries(fields.map((field) => [field.name, fieldLabel(field)]));
}

export function describeRule(rule: Rule, labels: Record<string, string> = {}): string {
  const field = (rule.field && labels[rule.field]) || rule.field || "字段";
  const value = rule.value ?? "";
  switch (rule.type) {
    case "number_percent_change":
      return `${field} ${OPERATORS[rule.operator ?? ""] ?? "变化"} ${value}% 及以上`;
    case "number_absolute_change":
      return `${field} ${OPERATORS[rule.operator ?? ""] ?? "变化"} ${value} 及以上`;
    case "threshold":
      return `${field} ${OPERATORS[rule.operator ?? ""] ?? "达到"} ${value}`;
    case "text_changed":
      return `${field} 的文本有变化`;
    case "keyword_present":
      return `出现“${rule.keyword ?? ""}”`;
    case "keyword_absent":
      return `不再出现“${rule.keyword ?? ""}”`;
    case "list_added":
      return `${field} 中出现新条目`;
    case "list_removed":
      return `${field} 中有条目消失`;
    case "list_updated":
      return `${field} 中的 ${(rule.watch_fields ?? []).join("、")} 有变化`;
    default:
      return `${field} 发生变化`;
  }
}

export function describeRules(rules: Rule[], mode?: string, labels: Record<string, string> = {}): string {
  if (rules.length === 0) return "页面内容有变化";
  return rules.map((rule) => describeRule(rule, labels)).join(mode === "all" ? "，并且 " : "，或 ");
}
