"""Monitor reads and commands."""
from uuid import UUID

from fastapi import APIRouter, Query

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.schemas.api import (
    JobView,
    MonitorDetail,
    MonitorRename,
    MonitorSettingsUpdate,
    MonitorView,
    Page,
    SnapshotDetail,
    SnapshotRecord,
    SpecVersion,
)
from webmonitor.services import monitors

router = APIRouter(prefix="/api/v1", tags=["monitors"])


@router.get("/monitors", response_model=Page[MonitorView])
async def list_monitors(session: DatabaseSession, user: AuthenticatedUser,
                        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                        archived: bool = False):
    return await monitors.list_monitors(session, user, limit, offset, archived=archived)


@router.get("/monitors/{monitor_id}", response_model=MonitorDetail)
async def read_monitor(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    return await monitors.read_monitor(session, user, monitor_id)


@router.get("/monitors/{monitor_id}/snapshots", response_model=Page[SnapshotRecord])
async def list_snapshots(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser,
                         limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await monitors.list_snapshots(session, user, monitor_id, limit, offset)


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotDetail)
async def read_snapshot(snapshot_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    return await monitors.read_snapshot(session, user, snapshot_id)


@router.get("/monitors/{monitor_id}/specs", response_model=Page[SpecVersion])
async def list_spec_versions(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser,
                             limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await monitors.list_spec_versions(session, user, monitor_id, limit, offset)


@router.patch("/monitors/{monitor_id}", response_model=MonitorView)
async def rename_monitor(monitor_id: UUID, body: MonitorRename, session: DatabaseSession,
                         user: AuthenticatedUser):
    monitor = await monitors.rename_monitor(session, user, monitor_id, body.name)
    result = monitors.monitor_view(monitor)
    await session.commit()
    return result


@router.patch("/monitors/{monitor_id}/settings", response_model=MonitorDetail)
async def update_monitor_settings(monitor_id: UUID, body: MonitorSettingsUpdate,
                                  session: DatabaseSession, user: AuthenticatedUser):
    await monitors.update_delivery_settings(session, user, monitor_id, body.settings)
    result = await monitors.read_monitor(session, user, monitor_id)
    await session.commit()
    return result


@router.post("/monitors/{monitor_id}/archive", response_model=MonitorView)
async def archive_monitor(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    monitor = await monitors.archive_monitor(session, user, monitor_id)
    result = monitors.monitor_view(monitor)
    await session.commit()
    return result


@router.post("/monitors/{monitor_id}/restore", response_model=MonitorView)
async def restore_monitor(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    monitor = await monitors.restore_monitor(session, user, monitor_id)
    result = monitors.monitor_view(monitor)
    await session.commit()
    return result


@router.get("/monitors/{monitor_id}/jobs", response_model=Page[JobView])
async def list_monitor_jobs(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser,
                            limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await monitors.list_monitor_jobs(session, user, monitor_id, limit, offset)


@router.post("/monitors/{monitor_id}/pause", response_model=MonitorView)
async def pause_monitor(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    monitor = await monitors.pause_monitor(session, user, monitor_id)
    result = monitors.monitor_view(monitor)
    await session.commit()
    return result


@router.post("/monitors/{monitor_id}/resume", response_model=MonitorView)
async def resume_monitor(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    monitor = await monitors.resume_monitor(session, user, monitor_id)
    result = monitors.monitor_view(monitor)
    await session.commit()
    return result


@router.post("/monitors/{monitor_id}/run", response_model=JobView, status_code=202)
async def run_now(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    from webmonitor.services.conversations import job_view
    job = await monitors.enqueue_manual(session, user, monitor_id)
    result = job_view(job)
    await session.commit()
    return result
