"""FastAPI factory: one process serves HTTP and runs every background loop."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

from webmonitor.api.routes import (
    auth,
    conversations,
    events,
    evidence,
    members,
    monitors,
    notifications,
)
from webmonitor.config import get_settings
from webmonitor.db import database_ready, get_engine, initialize_database
from webmonitor.errors import DomainError, domain_error_handler
from webmonitor.security.csrf import CSRFMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from agents import set_tracing_disabled
    set_tracing_disabled(True)
    await initialize_database()
    task = None
    if get_settings().workers_enabled:
        from webmonitor.worker import run_worker
        task = asyncio.create_task(run_worker())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        await get_engine().dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="WebMonitor", version="0.2.0", lifespan=lifespan,
                  openapi_url="/api/v1/openapi.json", docs_url=None, redoc_url=None)
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_middleware(CSRFMiddleware)
    for module in (auth, members, conversations, monitors, events, notifications, evidence):
        app.include_router(module.router)

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, exc: OperationalError):
        return await domain_error_handler(request, DomainError("database_unavailable", 503))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {
            "code": "validation_failed", "message": "Invalid request",
            "details": {"fields": [".".join(map(str, item["loc"])) for item in exc.errors()]}}})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        codes = {401: "unauthenticated", 403: "forbidden", 404: "not_found",
                 405: "method_not_allowed"}
        return JSONResponse(status_code=exc.status_code, content={"error": {
            "code": codes.get(exc.status_code, "request_failed"),
            "message": "Request rejected", "details": {}}})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled request failure", exc_info=exc)
        return await domain_error_handler(request,
            DomainError("internal_error", 500, "Request could not be completed"))

    @app.get("/api/v1/health/live")
    async def live():
        return {"status": "alive"}

    @app.get("/api/v1/health/ready")
    async def ready():
        if not await database_ready():
            raise DomainError("not_ready", 503, "Database is unavailable or uninitialized")
        return {"status": "ready"}

    return app
