"""Reusable MCP prompt workflows for monitor creation, editing and triage."""
from mcp.server.mcpserver import MCPServer

from webmonitor.mcp.auth import require_principal


def register_prompts(mcp: MCPServer) -> None:
    @mcp.prompt("create-monitor")
    def create_monitor_prompt(url: str, goal: str) -> str:
        """Guide the external model to discover a page, build a MonitorSpec, preview and confirm."""
        require_principal("read")
        return (
            f"Create a WebMonitor monitor for URL: {url}\n"
            f"Monitoring goal: {goal}\n\n"
            "Follow these steps:\n"
            "1. Read `webmonitor://schemas/monitor-spec`.\n"
            "2. Call `probe_target` on the URL first.\n"
            "3. If target values are in HTML, call `analyze_target(url, collection_mode='http')`. "
            "If the page is an empty SPA shell, call `capture_network(url)` and verify candidate "
            "JSON endpoints with `replay_request`. Only use `collection_mode='browser'` when HTTP "
            "and JSON APIs lack the data.\n"
            "4. Save a strict MonitorSpec via `save_monitor_draft`.\n"
            "5. Run `preview_monitor_draft` and verify the real extracted fields, coverage, and rules.\n"
            "6. Summarize what will be monitored and ask the user before calling `approve_draft` "
            "(or provide `approval_url` if the token lacks `drafts:approve`)."
        )

    @mcp.prompt("edit-monitor")
    def edit_monitor_prompt(monitor_id: str, change_request: str) -> str:
        """Guide incremental monitor modification via derive_draft_from_monitor."""
        require_principal("read")
        return (
            f"Modify existing monitor {monitor_id}.\n"
            f"Requested change: {change_request}\n\n"
            "Steps:\n"
            "1. Call `derive_draft_from_monitor(monitor_id)` to clone its current spec and settings.\n"
            "2. Re-probe or re-analyze the URL if selectors or endpoints are changing.\n"
            "3. Save changes via `save_monitor_draft` (contract) or `update_draft_settings` (schedule/delivery).\n"
            "4. Run `preview_monitor_draft` and summarize the diff before calling `approve_draft`."
        )

    @mcp.prompt("triage-failures")
    def triage_failures_prompt() -> str:
        """Guide diagnosis of failing monitors, jobs and deliveries."""
        require_principal("read")
        return (
            "Diagnose WebMonitor health issues:\n"
            "1. Call `list_monitors()` and check items with `health_status == 'failed'`.\n"
            "2. Read `webmonitor://events/unacknowledged` and `list_deliveries(status='failed')`.\n"
            "3. For failing monitors, inspect `list_monitor_jobs(monitor_id)` and `get_job(job_id)`.\n"
            "4. Summarize root causes and recommend whether to `run_monitor_now`, `retry_delivery`, "
            "`acknowledge_event`, or derive a new draft to fix changed selectors."
        )
