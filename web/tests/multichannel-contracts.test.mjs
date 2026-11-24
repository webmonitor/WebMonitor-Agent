import assert from "node:assert/strict";
import test from "node:test";
import { deliverySettingsSchema } from "../src/lib/api/preview.ts";

test("dual-channel settings retain per-event route overrides", () => {
  const settings = deliverySettingsSchema.parse({
    channel: "both",
    event_channels: { run_failed: "webhook" },
    notification_group_ids: ["6f7f4f3c-48a4-4a53-bf4a-a1ab7c8b1e6d"],
    webhook_url: "https://hooks.example.com/ops",
    schedule: { interval_seconds: 300, timezone: "UTC" },
  });
  assert.equal(settings.channel, "both");
  assert.deepEqual(settings.event_channels, { run_failed: "webhook" });
});
