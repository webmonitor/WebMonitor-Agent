"""Administrator operational overview."""
from fastapi import APIRouter, Query

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.schemas.observability import SystemMetrics
from webmonitor.services import metrics

router = APIRouter(prefix="/api/v1", tags=["administration"])


@router.get("/admin/metrics", response_model=SystemMetrics)
async def read_system_metrics(session: DatabaseSession, user: AuthenticatedUser,
                              hours: int = Query(24, ge=1, le=720)):
    return await metrics.system_metrics(session, user, hours)
