"""Safe MCP tool error mapping and bounded untrusted payload helpers."""
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from webmonitor.agent.tools import _validation_details
from webmonitor.errors import DomainError
from webmonitor.mcp.auth import require_principal
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.services.tokens import TokenPrincipal

logger = logging.getLogger(__name__)


def parse_uuid(value: str, *, field: str = "id") -> UUID:
    """Parse a UUID string or raise a structured 422 DomainError."""
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise DomainError(
            "validation_failed",
            422,
            f"Invalid UUID for {field}",
            details={"fields": [field]},
        ) from None


def coerce_spec_input(value: dict[str, Any] | str) -> MonitorSpec:
    """Accept a MonitorSpec mapping or JSON string and validate strictly."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise ValueError("spec must be a JSON object") from None
    return MonitorSpec.model_validate(value)


def safe_mcp_error(exc: Exception, *, is_spec: bool = False) -> dict[str, Any]:
    """Convert an exception into a safe, actionable MCP error envelope."""
    if isinstance(exc, DomainError):
        return {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details or {},
            }
        }
    if isinstance(exc, ValidationError):
        return {
            "error": {
                "code": "validation_failed",
                "message": "Invalid input; revise the reported fields.",
                "details": _validation_details(
                    exc.errors(include_input=False, include_context=False)
                ),
            }
        }
    if isinstance(exc, ValueError):
        return {
            "error": {
                "code": "validation_failed",
                "message": str(exc)[:300] or "Invalid input",
                "details": [{"field": "spec" if is_spec else "input", "message": str(exc)[:300]}],
            }
        }
    logger.error("MCP tool failed: %s", type(exc).__name__, exc_info=exc)
    return {
        "error": {
            "code": "tool_failed",
            "message": "Request could not be completed",
            "details": {},
        }
    }


def json_result(payload: Any, *, is_error: bool = False) -> CallToolResult:
    """Serialize a JSON payload into a standard MCP CallToolResult."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))],
        is_error=is_error,
    )


def bound_untrusted_json(
    data: Any, *, max_bytes: int = 8192, label: str = "untrusted_summary"
) -> dict[str, Any]:
    """Bound untrusted extracted page payloads so they cannot flood caller context."""
    encoded = json.dumps(data if data is not None else {}, ensure_ascii=False, default=str).encode(
        "utf-8"
    )
    if len(encoded) <= max_bytes:
        return {
            "untrusted": True,
            "truncated": False,
            "data": data,
            label: None,
        }
    return {
        "untrusted": True,
        "truncated": True,
        "data": None,
        label: encoded[:max_bytes].decode("utf-8", errors="ignore"),
    }


async def run_tool(
    scope: str,
    operation: Callable[[TokenPrincipal], Awaitable[CallToolResult | Any]],
    *,
    is_spec: bool = False,
) -> CallToolResult:
    """Enforce PAT scope and return either tool payload or structured is_error CallToolResult."""
    try:
        principal = require_principal(scope)
        outcome = await operation(principal)
        if isinstance(outcome, CallToolResult):
            return outcome
        return json_result(outcome)
    except Exception as exc:
        return json_result(safe_mcp_error(exc, is_spec=is_spec), is_error=True)
