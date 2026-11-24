import assert from "node:assert/strict";
import test from "node:test";
import {
  buildFieldDiffs,
  buildNumericTrends,
  chronologicalSnapshots,
  diffList,
  diffText,
  findPreviousSnapshot,
  parseNumericValue,
} from "../src/features/monitors/history-utils.ts";

const numberField = {
  name: "visitors",
  type: "number",
  normalize: { decimal_separator: ".", thousands_separator: "," },
};
const moneyField = {
  name: "price",
  type: "money",
  normalize: { decimal_separator: ",", thousands_separator: ".", currency: "EUR" },
};

function snapshot(id, collected_at, extracted_data) {
  return { id, collected_at, extracted_data };
}

test("numeric trends are chronological and omit missing and non-numeric values", () => {
  const rows = [
    snapshot("c", "2026-01-03T00:00:00Z", { visitors: "3,000", price: { amount: "30,00", currency: "EUR" } }),
    snapshot("a", "2026-01-01T00:00:00Z", { visitors: "1,000", price: { amount: "10,00", currency: "EUR" } }),
    snapshot("b", "2026-01-02T00:00:00Z", { visitors: "not available", price: null }),
    snapshot("d", "2026-01-04T00:00:00Z", {}),
  ];
  const originalOrder = rows.map((row) => row.id);
  const trends = buildNumericTrends(rows, [numberField, moneyField]);

  assert.deepEqual(trends[0].points, [
    { snapshotId: "a", collectedAt: "2026-01-01T00:00:00Z", value: 1000 },
    { snapshotId: "c", collectedAt: "2026-01-03T00:00:00Z", value: 3000 },
  ]);
  assert.deepEqual(trends[1].points.map((point) => point.value), [10, 30]);
  assert.deepEqual(rows.map((row) => row.id), originalOrder);
});

test("equal timestamps use snapshot ids as a deterministic tie-breaker", () => {
  const rows = [
    snapshot("b", "2026-01-01T00:00:00Z", {}),
    snapshot("a", "2026-01-01T00:00:00Z", {}),
  ];
  assert.deepEqual(chronologicalSnapshots(rows).map((row) => row.id), ["a", "b"]);
});

test("number and stored money parsing respects explicit separators and missing values", () => {
  assert.equal(parseNumericValue("1,234.50", numberField.normalize), 1234.5);
  assert.equal(parseNumericValue("-1.234,50", moneyField.normalize), -1234.5);
  assert.equal(parseNumericValue({ amount: "1.234,50", currency: "EUR" }, moneyField.normalize), 1234.5);
  assert.equal(parseNumericValue({ amount: "12.50", currency: "USD" }, moneyField.normalize), null);
  assert.equal(parseNumericValue(12.5, numberField.normalize), 12.5);

  for (const value of [undefined, null, "", "NaN", "Infinity", "1e3", "12 junk", "12,34", true, {}, Infinity]) {
    assert.equal(parseNumericValue(value, numberField.normalize), null, String(value));
  }
});

test("text diff reports equal, added and removed runs", () => {
  assert.deepEqual(diffText("same text", "same text"), [{ type: "equal", value: "same text" }]);
  assert.deepEqual(diffText("red fox", "red fox jumps"), [
    { type: "equal", value: "red fox" },
    { type: "added", value: " jumps" },
  ]);
  assert.deepEqual(diffText("red fox jumps", "red fox"), [
    { type: "equal", value: "red fox" },
    { type: "removed", value: " jumps" },
  ]);
  assert.deepEqual(diffText("the red fox", "the blue fox"), [
    { type: "equal", value: "the " },
    { type: "removed", value: "red" },
    { type: "added", value: "blue" },
    { type: "equal", value: " fox" },
  ]);
});

test("list diff reports added, removed and equal entries including canonical objects", () => {
  assert.deepEqual(diffList(["alpha", "beta"], ["beta", "gamma"]), [
    { type: "removed", value: "alpha" },
    { type: "equal", value: "beta" },
    { type: "added", value: "gamma" },
  ]);
  assert.deepEqual(diffList([{ id: 1, name: "one" }], [{ name: "one", id: 1 }, { id: 2 }]), [
    { type: "equal", value: { id: 1, name: "one" } },
    { type: "added", value: { id: 2 } },
  ]);
});

test("field diffs and previous lookup are empty when no prior snapshot exists", () => {
  const current = snapshot("only", "2026-01-01T00:00:00Z", { title: "first", items: ["one"] });
  const fields = [{ name: "title", type: "text" }, { name: "items", type: "list" }];
  assert.equal(findPreviousSnapshot([current], current.id), null);
  assert.deepEqual(buildFieldDiffs(fields, current.extracted_data, null), []);
  assert.deepEqual(buildFieldDiffs(fields, current.extracted_data, { title: "first", items: ["one"] }), []);
});
