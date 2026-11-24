export type McpClient = "cursor" | "claude";

/** Return a complete client config; JSON.stringify also escapes token text safely. */
export function mcpClientConfig(client: McpClient, origin: string, token: string): string {
  const url = new URL("/mcp", origin).toString();
  const server = client === "cursor"
    ? { url, headers: { Authorization: `Bearer ${token}` } }
    : {
        command: "npx",
        args: ["-y", "mcp-remote", url, "--header", `Authorization: Bearer ${token}`],
      };
  return JSON.stringify({ mcpServers: { webmonitor: server } }, null, 2);
}
