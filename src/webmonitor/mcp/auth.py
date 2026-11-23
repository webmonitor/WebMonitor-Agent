"""Bearer PAT authentication, scope checks and Origin validation for /mcp."""
from contextvars import ContextVar

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from webmonitor.config import get_settings
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.services import tokens
from webmonitor.services.tokens import TokenPrincipal

ALLOWED_MCP_METHODS = frozenset({"GET", "POST", "DELETE"})

_principal_var: ContextVar[TokenPrincipal | None] = ContextVar("mcp_principal", default=None)


def require_principal(scope: str | None = None) -> TokenPrincipal:
    """Return the authenticated PAT principal and enforce an optional scope."""
    principal = _principal_var.get()
    if principal is None:
        raise DomainError("unauthenticated", 401)
    if scope is not None and scope not in principal.scopes:
        raise DomainError(
            "insufficient_scope",
            403,
            f"Token missing required scope: {scope}",
            details={"required_scope": scope},
        )
    return principal


def validate_mcp_origin(request: Request) -> None:
    """Reject cross-origin browser requests while allowing non-browser local clients."""
    origins = request.headers.getlist("origin")
    if not origins:
        return
    if len(origins) != 1 or origins[0] not in get_settings().allowed_mcp_origins:
        raise DomainError("origin_invalid", 403)


def extract_bearer_token(request: Request) -> str:
    """Extract a single Bearer token from Authorization; cookies are never accepted."""
    headers = request.headers.getlist("authorization")
    if len(headers) != 1:
        raise DomainError("unauthenticated", 401)
    scheme, _, token = headers[0].strip().partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise DomainError("unauthenticated", 401)
    return token.strip()


def _error_response(exc: DomainError) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if exc.status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        headers=headers,
    )


class McpAuthASGIApp:
    """Authenticate /mcp requests with Bearer PAT and bind TokenPrincipal per request."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        if request.method.upper() not in ALLOWED_MCP_METHODS:
            response = _error_response(DomainError("method_not_allowed", 405, "Request rejected"))
            await response(scope, receive, send)
            return
        try:
            validate_mcp_origin(request)
            raw_token = extract_bearer_token(request)
            async with get_session_factory()() as session:
                principal = await tokens.resolve_token(session, raw_token)
        except DomainError as exc:
            response = _error_response(exc)
            await response(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(name.lower() == b"cache-control" for name, _ in headers):
                    headers.append((b"cache-control", b"no-store"))
                    message = {**message, "headers": headers}
            await send(message)

        token_ctx = _principal_var.set(principal)
        try:
            await self.app(scope, receive, send_no_store)
        finally:
            _principal_var.reset(token_ctx)
