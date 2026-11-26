/** A snapshot URL may only render history for the monitor that owns the row. */
export function snapshotMatchesMonitor<T extends { monitor_id: string }>(
  row: T | null | undefined,
  monitorId: string,
): row is T {
  return row?.monitor_id === monitorId;
}
