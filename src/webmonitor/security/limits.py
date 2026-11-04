"""Reject oversized request bodies before they are parsed or buffered."""
import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 1_048_576


class RequestTooLarge(Exception):
    """The client sent more bytes than any endpoint here accepts."""


def too_large_response() -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    body = json.dumps({"error": {"code": "request_too_large", "message": "request too large",
                                 "details": {"limit": MAX_BODY_BYTES}}}).encode("utf-8")
    headers = [(b"content-type", b"application/json"),
               (b"content-length", str(len(body)).encode()),
               (b"cache-control", b"no-store")]
    return 413, headers, body


class MaxBodyMiddleware:
    """Wire with app.add_middleware(MaxBodyMiddleware) as the outermost layer.

    A declared length is rejected before the body is read; an undeclared one is
    counted as it streams, so neither case can buffer the payload first. The
    middleware answers itself because it runs outside the exception-handler stack.
    """

    def __init__(self, app: ASGIApp, limit: int = MAX_BODY_BYTES):
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        if declared is not None and declared > self.limit:
            await _reject(send)
            return
        received = 0
        rejected = False

        async def counting() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    rejected = True
                    raise RequestTooLarge
            return message

        if rejected:
            await _reject(send)
            return
        try:
            await self.app(scope, counting, send)
        except RequestTooLarge:
            await _reject(send)


async def _reject(send: Send) -> None:
    status, headers, body = too_large_response()
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def _content_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
