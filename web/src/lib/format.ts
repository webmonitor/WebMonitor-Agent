export function formatTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(date);
}

export function formatJson(value: unknown): string {
  if (value === null || value === undefined) return "—";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

const LABELS: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  succeeded: "成功",
  failed: "失败",
  cancelled: "已取消",
  discarded: "已丢弃",
  active: "运行中",
  paused: "已暂停",
  draft: "草稿",
  published: "已发布",
  healthy: "正常",
  pending_first_success: "等待首次成功",
  ready: "已建立基线",
  sent: "已发送",
  sending: "发送中",
  retrying: "重试中",
  price_changed: "价格变化",
  list_changed: "列表变化",
  content_changed: "内容变化",
  run_failed: "采集失败",
  recovered: "已恢复",
  http: "HTTP",
  browser: "浏览器",
};

export function statusLabel(status?: string | null): string {
  if (!status) return "—";
  return LABELS[status] ?? status;
}

export function baselineLabel(status?: string | null): string {
  if (status === "ready") return "已建立基线";
  if (status === "pending_first_success") return "等待首次成功";
  return statusLabel(status);
}
