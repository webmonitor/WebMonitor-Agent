export type SnapshotLike = {
  id: string;
  collected_at: string;
  extracted_data: Record<string, unknown>;
};

export type NumericNormalization = {
  decimal_separator?: "." | "," | null;
  thousands_separator?: "." | "," | " " | "'" | null;
  currency?: string | null;
};

export type HistoryField = {
  name: string;
  type: string;
  semantic?: string | null;
  normalize?: NumericNormalization | null;
};

export type NumericTrendPoint = {
  snapshotId: string;
  collectedAt: string;
  value: number;
};

export type NumericTrend = {
  field: HistoryField;
  points: NumericTrendPoint[];
};

export type DiffType = "equal" | "added" | "removed";
export type TextDiffPart = { type: DiffType; value: string };
export type ListDiffPart = { type: DiffType; value: unknown };

export type FieldDiff =
  | { field: HistoryField; kind: "text"; parts: TextDiffPart[] }
  | { field: HistoryField; kind: "list"; parts: ListDiffPart[] };

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

/** Oldest first, with explicit fallbacks for equal or invalid timestamps. */
export function chronologicalSnapshots<T extends SnapshotLike>(snapshots: readonly T[]): T[] {
  return [...snapshots].sort((left, right) => {
    const leftTime = Date.parse(left.collected_at);
    const rightTime = Date.parse(right.collected_at);
    const leftValid = Number.isFinite(leftTime);
    const rightValid = Number.isFinite(rightTime);
    if (leftValid && rightValid && leftTime !== rightTime) return leftTime - rightTime;
    if (leftValid !== rightValid) return leftValid ? -1 : 1;
    return compareText(left.collected_at, right.collected_at) || compareText(left.id, right.id);
  });
}

/** The row immediately before the current one in an already chronological list. */
export function findPreviousSnapshot<T extends SnapshotLike>(
  chronological: readonly T[],
  currentId: string,
): T | null {
  const index = chronological.findIndex((snapshot) => snapshot.id === currentId);
  return index > 0 ? chronological[index - 1] ?? null : null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function parseDecimal(value: unknown, normalization: NumericNormalization): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const raw = value.trim();
  if (!raw) return null;

  // Stored numbers use the same explicit, non-exponential notation as collection.
  const decimal = normalization.decimal_separator ?? ".";
  const thousands = normalization.thousands_separator;
  const integer = thousands == null
    ? "[0-9]+"
    : `(?:[0-9]+|[0-9]{1,3}(?:${escapeRegExp(thousands)}[0-9]{3})+)`;
  const pattern = new RegExp(`^[+-]?${integer}(?:${escapeRegExp(decimal)}[0-9]+)?$`);
  if (!pattern.test(raw)) return null;

  const ungrouped = thousands == null ? raw : raw.split(thousands).join("");
  const parsed = Number(ungrouped.replace(decimal, "."));
  return Number.isFinite(parsed) ? parsed : null;
}

/** Parse a stored number or a stored money object's amount; invalid values stay out of trends. */
export function parseNumericValue(
  value: unknown,
  normalization: NumericNormalization = {},
): number | null {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const money = value as { amount?: unknown; currency?: unknown };
    if (!("amount" in money)) return null;
    if (normalization.currency != null && money.currency !== normalization.currency) return null;
    return parseDecimal(money.amount, normalization);
  }
  return parseDecimal(value, normalization);
}

/** Numeric fields retain spec order; points are chronological and omit missing/invalid values. */
export function buildNumericTrends(
  snapshots: readonly SnapshotLike[],
  fields: readonly HistoryField[],
): NumericTrend[] {
  const chronological = chronologicalSnapshots(snapshots);
  const trends: NumericTrend[] = [];
  for (const field of fields) {
    if (field.type !== "number" && field.type !== "money") continue;
    const points: NumericTrendPoint[] = [];
    for (const snapshot of chronological) {
      const value = parseNumericValue(
        snapshot.extracted_data[field.name],
        field.normalize ?? {},
      );
      if (value === null) continue;
      points.push({ snapshotId: snapshot.id, collectedAt: snapshot.collected_at, value });
    }
    trends.push({ field, points });
  }
  return trends;
}

function listItemKey(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return `array:[${value.map(listItemKey).join(",")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => compareText(left, right));
    return `object:{${entries.map(([key, item]) => `${JSON.stringify(key)}:${listItemKey(item)}`).join(",")}}`;
  }
  return `${typeof value}:${JSON.stringify(value) ?? String(value)}`;
}

function sequenceDiff<T>(
  before: readonly T[],
  after: readonly T[],
  key: (value: T) => string,
): { type: DiffType; value: T }[] {
  const lengths: Uint32Array[] = Array.from(
    { length: before.length + 1 },
    () => new Uint32Array(after.length + 1),
  );
  for (let left = before.length - 1; left >= 0; left -= 1) {
    for (let right = after.length - 1; right >= 0; right -= 1) {
      lengths[left][right] = key(before[left]) === key(after[right])
        ? lengths[left + 1][right + 1] + 1
        : Math.max(lengths[left + 1][right], lengths[left][right + 1]);
    }
  }

  const parts: { type: DiffType; value: T }[] = [];
  let left = 0;
  let right = 0;
  while (left < before.length && right < after.length) {
    if (key(before[left]) === key(after[right])) {
      parts.push({ type: "equal", value: before[left] });
      left += 1;
      right += 1;
    } else if (lengths[left + 1][right] >= lengths[left][right + 1]) {
      parts.push({ type: "removed", value: before[left] });
      left += 1;
    } else {
      parts.push({ type: "added", value: after[right] });
      right += 1;
    }
  }
  while (left < before.length) {
    parts.push({ type: "removed", value: before[left] });
    left += 1;
  }
  while (right < after.length) {
    parts.push({ type: "added", value: after[right] });
    right += 1;
  }
  return parts;
}

/** Word-level diff which preserves whitespace and coalesces adjacent runs. */
export function diffText(before: string, after: string): TextDiffPart[] {
  const oldTokens = before.split(/(\s+)/u).filter(Boolean);
  const newTokens = after.split(/(\s+)/u).filter(Boolean);
  const parts = sequenceDiff(oldTokens, newTokens, (token) => token);
  const merged: TextDiffPart[] = [];
  for (const part of parts) {
    const previous = merged[merged.length - 1];
    if (previous?.type === part.type) previous.value += part.value;
    else merged.push({ ...part });
  }
  return merged;
}

/** Exact list-entry diff; object keys are canonicalized so serialization order is irrelevant. */
export function diffList(before: readonly unknown[], after: readonly unknown[]): ListDiffPart[] {
  return sequenceDiff(before, after, listItemKey);
}

/** Changed text/list fields only. A missing previous snapshot is not an all-added diff. */
export function buildFieldDiffs(
  fields: readonly HistoryField[],
  current: Record<string, unknown>,
  previous: Record<string, unknown> | null,
): FieldDiff[] {
  if (previous === null) return [];
  const diffs: FieldDiff[] = [];
  for (const field of fields) {
    const oldValue = previous[field.name];
    const newValue = current[field.name];
    if (field.type === "text") {
      const before = oldValue == null ? "" : typeof oldValue === "string" ? oldValue : null;
      const after = newValue == null ? "" : typeof newValue === "string" ? newValue : null;
      if (before === null || after === null) continue;
      const parts = diffText(before, after);
      if (parts.some((part) => part.type !== "equal")) {
        diffs.push({ field, kind: "text", parts });
      }
    } else if (field.type === "list") {
      const before = oldValue == null ? [] : Array.isArray(oldValue) ? oldValue : null;
      const after = newValue == null ? [] : Array.isArray(newValue) ? newValue : null;
      if (before === null || after === null) continue;
      const parts = diffList(before, after);
      if (parts.some((part) => part.type !== "equal")) {
        diffs.push({ field, kind: "list", parts });
      }
    }
  }
  return diffs;
}
