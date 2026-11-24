import assert from "node:assert/strict";
import test from "node:test";
import { monitorSpecSchema } from "../src/lib/api/preview.ts";

function specWith(pagination) {
  return {
    name: "Paginated API",
    url: "https://example.com/api",
    collection_mode: "http",
    fields: [{
      name: "items", type: "list", semantic: "Items", path: "data.list",
      item_fields: [{ name: "id", type: "text", semantic: "ID", path: "id" }],
    }],
    business_key: { field: "items", item_fields: ["id"] },
    change_rules: { mode: "any", rules: [{ type: "list_added", field: "items" }] },
    coverage: { scope: "full", description: "All pages" },
    source: {
      kind: "json",
      steps: [{ id: "list", request: { method: "GET", url: "https://example.com/api" } }],
      pagination,
    },
  };
}

test("cursor and offset pagination retain their transport-specific fields", () => {
  const cursor = monitorSpecSchema.parse(specWith({
    kind: "cursor", next_cursor_path: "data.next", size_param: "limit", size: 20,
  }));
  assert.equal(cursor.source.pagination.cursor_param, "cursor");
  assert.equal(cursor.source.pagination.location, "query");

  const offset = monitorSpecSchema.parse(specWith({
    kind: "offset", start_offset: 20, offset_param: "skip", size_param: "limit", size: 20,
  }));
  assert.equal(offset.source.pagination.start_offset, 20);
  assert.equal(offset.source.pagination.offset_param, "skip");
});

test("POST body pagination preserves the body location", () => {
  const spec = specWith({ kind: "page", location: "body", size_param: "size", size: 20 });
  spec.source.steps[0].request = {
    method: "POST", url: "https://example.com/api", body: { query: "notice" },
  };
  const parsed = monitorSpecSchema.parse(spec);
  assert.equal(parsed.source.pagination.location, "body");
  assert.deepEqual(parsed.source.steps[0].request.body, { query: "notice" });
});
