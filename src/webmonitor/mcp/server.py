"""MCP server factory wiring tools, resources, prompts and Streamable HTTP ASGI."""
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp

from webmonitor.mcp.auth import McpAuthASGIApp
from webmonitor.mcp.instructions import MCP_INSTRUCTIONS
from webmonitor.mcp.prompts import register_prompts
from webmonitor.mcp.resources import register_resources
from webmonitor.mcp.tools_discover import register_discover_tools
from webmonitor.mcp.tools_drafts import register_draft_tools
from webmonitor.mcp.tools_ops import register_ops_tools
from webmonitor.mcp.tools_read import register_read_tools


def build_mcp_runtime() -> tuple[ASGIApp, StreamableHTTPSessionManager]:
    """Build a fresh stateless Streamable HTTP MCP server and auth-wrapped ASGI handler."""
    mcp = MCPServer(
        name="WebMonitor",
        instructions=MCP_INSTRUCTIONS,
    )
    register_discover_tools(mcp)
    register_draft_tools(mcp)
    register_read_tools(mcp)
    register_ops_tools(mcp)
    register_resources(mcp)
    register_prompts(mcp)

    # Initialize the SDK's StreamableHTTPSessionManager in stateless JSON mode;
    # McpAuthASGIApp enforces Bearer PAT auth and Origin validation before it.
    mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    session_manager = mcp.session_manager
    return McpAuthASGIApp(session_manager.handle_request), session_manager
