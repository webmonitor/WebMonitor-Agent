export function isTerminalJobStatus(status: string): boolean {
  return status !== "queued" && status !== "running";
}

/** Every view derived from a completed check refreshes from the same transition. */
export function finishedRunQueryKeys(monitorId: string): readonly (readonly unknown[])[] {
  return [
    ["monitor-jobs", monitorId],
    ["monitor", monitorId],
    ["events"],
    ["snapshots", monitorId],
    ["events", "unread-count"],
  ];
}
