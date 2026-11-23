"""Discovery tools dispatched as worker `analyze` jobs over egress."""
import asyncio
from datetime import timedelta
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations
from sqlalchemy import select

from webmonitor.config import get_settings
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.mcp.errors import run_tool
from webmonitor.models import Job, utc_now
from webmonitor.schemas.monitors import ApiRequest
from webmonitor.security.egress import validate_url
from webmonitor.services import jobs

ANALYSIS_REUSE_SECONDS = 900
READ_ONLY_EXTERNAL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)


def _clamp_timeout(seconds: int, *, minimum: int = 5, maximum: int = 120) -> float:
    return float(min(max(int(seconds), minimum), maximum))


async def _wait_with_progress(
    job_id,
    *,
    timeout: float,
    cancel_on_timeout: bool,
    ctx: Context | None,
) -> Job:
    if ctx is None:
        return await jobs.wait(job_id, timeout=timeout, cancel_on_timeout=cancel_on_timeout)

    async def pulse() -> None:
        step = 0
        while True:
            await asyncio.sleep(2.0)
            step += 1
            try:
                await ctx.report_progress(step, None, f"Waiting for worker job {job_id}")
            except Exception:
                return

    ticker = asyncio.create_task(pulse())
    try:
        return await jobs.wait(job_id, timeout=timeout, cancel_on_timeout=cancel_on_timeout)
    finally:
        ticker.cancel()
        await asyncio.gather(ticker, return_exceptions=True)


async def _enqueue_analyze(
    *,
    user_id,
    url: str,
    spec: dict[str, Any],
) -> Job:
    settings = get_settings()
    async with get_session_factory()() as session:
        await jobs.enforce_hourly_quota(
            session,
            user_id=user_id,
            kind="analyze",
            limit=settings.analyze_runs_per_hour,
        )
        created = await jobs.enqueue(
            session,
            user_id=user_id,
            kind="analyze",
            url=url,
            spec=spec,
        )
        await session.commit()
        return created


def _analysis_payload(job: Job) -> dict[str, Any]:
    result = job.result or {}
    return {
        "job_id": str(job.id),
        "final_url": result.get("final_url"),
        "analyzed_at": job.created_at.isoformat() if job.created_at else None,
        "untrusted_page_data": True,
        "analysis": result.get("analysis") or {},
        "coverage": result.get("coverage") or {},
        "warnings": result.get("warnings") or [],
    }


def register_discover_tools(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY_EXTERNAL)
    async def probe_target(
        url: str,
        timeout_seconds: int = 40,
        ctx: Context | None = None,
    ) -> CallToolResult:
        """Fetch a public URL once via worker egress and inspect payload markers, text sample, comments, scripts or JSON summary."""

        async def op(principal):
            target = validate_url(url)
            created = await _enqueue_analyze(
                user_id=principal.user.user_id,
                url=target,
                spec={"collection_mode": "http", "op": "probe"},
            )
            finished = await _wait_with_progress(
                created.id,
                timeout=_clamp_timeout(timeout_seconds),
                cancel_on_timeout=True,
                ctx=ctx,
            )
            result = finished.result or {}
            return {
                "job_id": str(finished.id),
                "untrusted_page_data": True,
                "probe": result.get("probe") or {},
            }

        return await run_tool("discover", op)

    @mcp.tool(annotations=READ_ONLY_EXTERNAL)
    async def analyze_target(
        url: str,
        collection_mode: Literal["http", "browser"] = "http",
        timeout_seconds: int = 70,
        ctx: Context | None = None,
    ) -> CallToolResult:
        """Inspect a page structurally via a collection job. Always run HTTP first; browser mode requires recent HTTP evidence for the same URL."""

        async def op(principal):
            if collection_mode not in {"http", "browser"}:
                raise DomainError("validation_failed", 422, details={"fields": ["collection_mode"]})
            target = validate_url(url)
            cutoff = utc_now() - timedelta(seconds=ANALYSIS_REUSE_SECONDS)
            async with get_session_factory()() as session:
                prior = (
                    await session.scalars(
                        select(Job).where(
                            Job.user_id == principal.user.user_id,
                            Job.kind == "analyze",
                            Job.url == target,
                            Job.status == "succeeded",
                            Job.created_at >= cutoff,
                        )
                        .order_by(Job.created_at.desc())
                    )
                ).all()
                if collection_mode == "browser":
                    has_http = any(
                        item.spec
                        and item.spec.get("collection_mode") == "http"
                        and item.spec.get("op") in (None, "probe")
                        for item in prior
                    )
                    if not has_http:
                        raise DomainError("http_analysis_required", 409)
                else:
                    reusable = next(
                        (
                            item
                            for item in prior
                            if item.spec
                            and item.spec.get("collection_mode") == "http"
                            and item.spec.get("op") is None
                        ),
                        None,
                    )
                    if reusable is not None:
                        return _analysis_payload(reusable)

            created = await _enqueue_analyze(
                user_id=principal.user.user_id,
                url=target,
                spec={"collection_mode": collection_mode},
            )
            finished = await _wait_with_progress(
                created.id,
                timeout=_clamp_timeout(timeout_seconds),
                cancel_on_timeout=True,
                ctx=ctx,
            )
            return _analysis_payload(finished)

        return await run_tool("discover", op)

    @mcp.tool(annotations=READ_ONLY_EXTERNAL)
    async def capture_network(
        url: str,
        timeout_seconds: int = 70,
        ctx: Context | None = None,
    ) -> CallToolResult:
        """Render the page once in the sandboxed browser and capture XHR/Fetch JSON candidates."""

        async def op(principal):
            target = validate_url(url)
            created = await _enqueue_analyze(
                user_id=principal.user.user_id,
                url=target,
                spec={"collection_mode": "browser", "op": "network"},
            )
            finished = await _wait_with_progress(
                created.id,
                timeout=_clamp_timeout(timeout_seconds),
                cancel_on_timeout=True,
                ctx=ctx,
            )
            return _analysis_payload(finished)

        return await run_tool("discover", op)

    @mcp.tool(annotations=READ_ONLY_EXTERNAL)
    async def replay_request(
        request: dict[str, Any],
        timeout_seconds: int = 40,
        ctx: Context | None = None,
    ) -> CallToolResult:
        """Send one concrete HTTP request over worker egress and summarize the JSON/text response."""

        async def op(principal):
            parsed = ApiRequest.model_validate(request)
            target = validate_url(parsed.url)
            created = await _enqueue_analyze(
                user_id=principal.user.user_id,
                url=target,
                spec={
                    "collection_mode": "http",
                    "op": "replay",
                    "request": parsed.model_dump(mode="json"),
                },
            )
            finished = await _wait_with_progress(
                created.id,
                timeout=_clamp_timeout(timeout_seconds),
                cancel_on_timeout=True,
                ctx=ctx,
            )
            result = finished.result or {}
            return {
                "job_id": str(finished.id),
                "untrusted_page_data": True,
                "replay": result.get("replay") or {},
            }

        return await run_tool("discover", op)
