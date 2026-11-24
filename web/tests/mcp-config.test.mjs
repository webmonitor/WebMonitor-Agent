import assert from "node:assert/strict";
import test from "node:test";
import { mcpClientConfig } from "../src/features/tokens/mcp-config.ts";

test("Cursor config uses the streamable HTTP endpoint and bearer authentication", () => {
  const config = JSON.parse(mcpClientConfig("cursor", "https://monitor.example.com/base", "secret"));
  assert.deepEqual(config, {
    mcpServers: {
      webmonitor: {
        url: "https://monitor.example.com/mcp",
        headers: { Authorization: "Bearer secret" },
      },
    },
  });
});

test("Claude Desktop config bridges HTTP through mcp-remote without shell interpolation", () => {
  const config = JSON.parse(mcpClientConfig("claude", "http://localhost:8080", 'quote"\\value'));
  assert.deepEqual(config.mcpServers.webmonitor.args, [
    "-y",
    "mcp-remote",
    "http://localhost:8080/mcp",
    "--header",
    'Authorization: Bearer quote"\\value',
  ]);
});
