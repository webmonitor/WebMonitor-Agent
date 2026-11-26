import assert from "node:assert/strict";
import test from "node:test";
import { mergePages, nextPageOffset, pageRefetchInterval } from "../src/lib/api/pagination.ts";
import { finishedRunQueryKeys, isTerminalJobStatus } from "../src/lib/api/job-lifecycle.ts";
import {
  archivedConversationRedirect,
  operationIsCurrent,
  preservesDraftRoute,
  runAnnouncement,
} from "../src/features/chat/chat-state.ts";
import {
  frozenTemplateName,
  missingGroupIds,
  withSelectedTemplate,
} from "../src/features/monitors/delivery-settings-utils.ts";
import { snapshotMatchesMonitor } from "../src/features/monitors/snapshot-page-utils.ts";
import { titleKey } from "../src/lib/i18n/title.ts";

test("offset pagination reaches and retains records beyond twenty pages", () => {
  const rows = Array.from({ length: 55 }, (_, index) => ({ id: `row-${index}` }));
  const pages = [];
  let offset = 0;
  while (offset !== undefined) {
    pages.push({ items: rows.slice(offset, offset + 2), total: rows.length });
    offset = nextPageOffset(pages, offset, 2);
    assert.ok(pages.length <= rows.length, "pagination must keep moving forward");
  }
  assert.ok(pages.length > 20);
  assert.deepEqual(mergePages(pages).items, rows);
});

test("overlapping pages replace duplicate rows without dropping earlier pages", () => {
  const pages = [
    { items: [{ id: "a", value: 1 }, { id: "b", value: 1 }], total: 4 },
    { items: [{ id: "b", value: 2 }, { id: "c", value: 2 }], total: 4 },
  ];
  assert.equal(nextPageOffset(pages, 1, 2), 3);
  assert.deepEqual(mergePages(pages), {
    items: [{ id: "a", value: 1 }, { id: "b", value: 2 }, { id: "c", value: 2 }],
    total: 4,
  });
  assert.equal(pageRefetchInterval(2, 15_000), 60_000);
  assert.equal(pageRefetchInterval(1, 15_000), 15_000);
});

test("terminal manual runs invalidate every derived monitor view", () => {
  assert.equal(isTerminalJobStatus("queued"), false);
  assert.equal(isTerminalJobStatus("running"), false);
  for (const status of ["succeeded", "failed", "cancelled", "discarded"]) {
    assert.equal(isTerminalJobStatus(status), true);
  }
  assert.deepEqual(finishedRunQueryKeys("monitor-id"), [
    ["monitor-jobs", "monitor-id"],
    ["monitor", "monitor-id"],
    ["events"],
    ["snapshots", "monitor-id"],
    ["events", "unread-count"],
  ]);
});

test("chat completions are scoped by operation sequence and conversation route", () => {
  const operation = { conversationId: "a", sequence: 4 };
  assert.equal(operationIsCurrent(operation, 4, "a"), true);
  assert.equal(operationIsCurrent(operation, 5, "a"), false);
  assert.equal(operationIsCurrent(operation, 4, "b"), false);

  const created = { conversationId: null, sequence: 5 };
  assert.equal(operationIsCurrent(created, 5, "created-id", "created-id"), true);
  assert.equal(operationIsCurrent(created, 5, "another-id", "created-id"), false);
  assert.equal(preservesDraftRoute(null, "created-id", "created-id"), true);
  assert.equal(preservesDraftRoute(null, "another-id", "created-id"), false);
  assert.equal(preservesDraftRoute("a", "b", "b"), false);
});

test("archiving an old row cannot navigate away from a newly selected conversation", () => {
  assert.equal(archivedConversationRedirect("/app", "?conversation=b", "a"), null);
  assert.equal(archivedConversationRedirect("/app", "?conversation=a", "a"), "/app");
  assert.equal(archivedConversationRedirect("/app/monitors", "?conversation=a", "a"), null);
});

test("live announcements cover only run lifecycle transitions", () => {
  const queued = { conversationId: "a", jobId: "job", status: "queued" };
  assert.equal(runAnnouncement(null, { ...queued, status: "succeeded" }), null);
  assert.equal(runAnnouncement(null, queued), "started");
  assert.equal(runAnnouncement(queued, { ...queued, status: "running" }), null);
  assert.equal(runAnnouncement(queued, { ...queued, status: "succeeded" }), "completed");
  assert.equal(runAnnouncement(queued, { ...queued, status: "failed" }), "failed");
  assert.equal(runAnnouncement(queued, { ...queued, status: "cancelled" }), "cancelled");
  assert.equal(
    runAnnouncement({ ...queued, status: "succeeded" }, { ...queued, status: "succeeded" }),
    null,
  );
  assert.equal(
    runAnnouncement({ ...queued, status: "cancelled" }, { ...queued, status: "running" }),
    null,
  );
});

test("unloaded delivery pages never mark selected groups missing", () => {
  assert.deepEqual(missingGroupIds(["later", "loaded"], ["loaded"], true), []);
  assert.deepEqual(missingGroupIds(["later", "loaded"], ["loaded"], false), ["later"]);
});

test("an off-page selected template retains its frozen name and exact value", () => {
  const options = withSelectedTemplate(
    [{ value: "", label: "System default" }, { value: "loaded", label: "Loaded" }],
    "stored-template",
    frozenTemplateName({ name: "Frozen design" }),
    "Selected template",
  );
  assert.deepEqual(options.at(-1), { value: "stored-template", label: "Frozen design" });
  assert.equal(withSelectedTemplate(options, "loaded", null, "fallback"), options);
});

test("snapshot ownership rejects a valid row mounted under another monitor", () => {
  const row = { id: "snapshot", monitor_id: "monitor-a" };
  assert.equal(snapshotMatchesMonitor(row, "monitor-a"), true);
  assert.equal(snapshotMatchesMonitor(row, "monitor-b"), false);
  assert.equal(snapshotMatchesMonitor(undefined, "monitor-a"), false);
});

test("every app route has a title and concrete records win over parent routes", () => {
  const routes = new Map([
    ["/app", "common.title.workspace"],
    ["/app/events", "common.title.events"],
    ["/app/notifications", "common.title.notifications"],
    ["/app/templates", "common.title.templates"],
    ["/app/tokens", "common.title.tokens"],
    ["/app/members", "common.title.members"],
    ["/app/system", "system.title"],
    ["/app/archived-conversations", "chat.archive.title"],
    ["/app/archived", "common.title.archived"],
    ["/app/monitors", "common.title.monitors"],
    ["/app/monitors/monitor-id", "common.title.monitor"],
    ["/app/monitors/monitor-id/snapshots/snapshot-id", "common.title.snapshot"],
  ]);
  for (const [pathname, key] of routes) assert.equal(titleKey(pathname), key, pathname);
  assert.equal(titleKey("/app/monitors/monitor-id/snapshots/snapshot-id/"), "common.title.snapshot");
});
