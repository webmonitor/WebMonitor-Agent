import assert from "node:assert/strict";
import test from "node:test";
import { api, ApiError, clearCsrfToken, safeReturnTo } from "../src/lib/api/client.ts";
import { deliveryPreviewSchema, deliverySettingsSchema, monitorSpecSchema } from "../src/lib/api/preview.ts";
import { clearSubmittedDraft } from "../src/lib/draft.ts";

Object.assign(globalThis, {
  window: {
    location: { origin: "https://monitor.example" },
    dispatchEvent: () => true,
  },
});

test("safeReturnTo preserves a same-origin workspace query and fragment", () => {
  assert.equal(
    safeReturnTo("/app/events?unread=1&type=list_changed#event-2"),
    "/app/events?unread=1&type=list_changed#event-2",
  );
  assert.equal(safeReturnTo("https://evil.example/app?unread=1"), "/app");
  assert.equal(safeReturnTo("//evil.example/app"), "/app");
  assert.equal(safeReturnTo("/other?unread=1"), "/app");
});

test("a CSRF transport failure is a structured network ApiError", async () => {
  const originalFetch = globalThis.fetch;
  clearCsrfToken();
  globalThis.fetch = async () => { throw new TypeError("offline"); };
  try {
    await assert.rejects(
      api("/monitors", { method: "POST", body: "{}" }),
      (failure) => failure instanceof ApiError
        && failure.code === "network_unavailable"
        && failure.status === 0,
    );
  } finally {
    globalThis.fetch = originalFetch;
    clearCsrfToken();
  }
});

test("composer clearing compares the exact submitted draft", () => {
  const submitted = "  watch the price  ";
  assert.equal(clearSubmittedDraft(submitted, submitted), "");
  assert.equal(clearSubmittedDraft(`${submitted}\nnext request`, submitted), `${submitted}\nnext request`);
  assert.equal(clearSubmittedDraft("watch the price", submitted), "watch the price");
});

const validSpec = {
  name: "Course changes",
  url: "https://example.edu/courses",
  collection_mode: "http",
  fields: [{ name: "title", type: "text", semantic: "Course title", selector: "h1" }],
  change_rules: { mode: "any", rules: [{ type: "text_changed", field: "title" }] },
  coverage: { scope: "full", description: "The complete notice page" },
};

test("monitor spec accepts a valid minimal production contract", () => {
  const parsed = monitorSpecSchema.safeParse(validSpec);
  assert.equal(parsed.success, true);
  if (parsed.success) {
    assert.equal(parsed.data.fields[0]?.required, true);
    assert.equal(parsed.data.change_rules.consecutive_hits, 1);
    assert.deepEqual(parsed.data.browser_steps, []);
  }
});

test("monitor spec accepts value, regex and consecutive confirmation rules", () => {
  const parsed = monitorSpecSchema.safeParse({
    ...validSpec,
    fields: [{ name: "link", type: "url", semantic: "Course link", selector: "a" }],
    change_rules: {
      mode: "any",
      consecutive_hits: 2,
      rules: [
        { type: "value_changed", field: "link" },
        { type: "regex_match", field: "link", pattern: "^https:" },
      ],
    },
  });
  assert.equal(parsed.success, true);
  if (parsed.success) assert.equal(parsed.data.change_rules.consecutive_hits, 2);
});

test("monitor spec accepts serialized null item_fields on scalar list entries", () => {
  const parsed = monitorSpecSchema.safeParse({
    ...validSpec,
    fields: [{
      name: "courses",
      type: "list",
      semantic: "Available courses",
      selector: ".course",
      item_fields: [{
        name: "title",
        type: "text",
        semantic: "Course title",
        selector: "h2",
        item_fields: null,
      }],
    }],
    business_key: { field: "courses", item_fields: ["title"] },
    change_rules: { mode: "any", rules: [{ type: "list_added", field: "courses" }] },
  });
  assert.equal(parsed.success, true);
});

test("monitor spec rejects missing required sections and empty min-one collections", () => {
  for (const key of ["name", "url", "collection_mode", "change_rules", "coverage"]) {
    const value = { ...validSpec };
    delete value[key];
    assert.equal(monitorSpecSchema.safeParse(value).success, false, key);
  }
  assert.equal(monitorSpecSchema.safeParse({ ...validSpec, fields: [] }).success, false);
  assert.equal(monitorSpecSchema.safeParse({
    ...validSpec,
    change_rules: { mode: "any", rules: [] },
  }).success, false);
  assert.equal(monitorSpecSchema.safeParse({
    ...validSpec,
    business_key: { field: "title", item_fields: [] },
  }).success, false);
});

test("delivery settings preserve timing fields and old JSON defaults", () => {
  const legacy = deliverySettingsSchema.safeParse({ notification_group_ids: [] });
  assert.equal(legacy.success, true);
  if (legacy.success) {
    assert.equal(legacy.data.notification_cooldown_seconds, 0);
    assert.equal(legacy.data.quiet_hours, undefined);
  }
  const timed = deliverySettingsSchema.safeParse({
    notification_group_ids: [],
    notification_cooldown_seconds: 300,
    quiet_hours: { start: "22:00", end: "07:00" },
  });
  assert.equal(timed.success, true);
  assert.equal(deliverySettingsSchema.safeParse({
    notification_group_ids: [],
    quiet_hours: { start: "22:00", end: "22:00" },
  }).success, false);
});

test("delivery preview retains a protected recipient count without addresses", () => {
  const parsed = deliveryPreviewSchema.safeParse({
    preview_id: "preview-1",
    settings_revision: 3,
    settings_hash: "settings-hash",
    channel: "email",
    template_hash: "template-hash",
    rendered_emails: [],
    recipients: [],
    recipient_count: 2,
    recipient_sources: [],
    warnings: [],
    created_at: "2026-01-01T00:00:00Z",
    expires_at: "2026-01-01T01:00:00Z",
  });
  assert.equal(parsed.success, true);
  if (parsed.success) {
    assert.deepEqual(parsed.data.recipients, []);
    assert.equal(parsed.data.recipient_count, 2);
  }
});
