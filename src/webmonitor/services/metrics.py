"""Bounded operational aggregates over the existing jobs protocol."""
from datetime import timedelta

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.models import Delivery, Job, User, utc_now
from webmonitor.schemas.observability import (
    CollectionMetric,
    DeliveryMetric,
    QueueMetric,
    SystemMetrics,
    UsageMetric,
)
from webmonitor.security.auth import CurrentUser, require_admin


async def system_metrics(session: AsyncSession, user: CurrentUser, hours: int) -> SystemMetrics:
    require_admin(user)
    now = utc_now()
    cutoff = now - timedelta(hours=hours)

    queue_rows = (await session.execute(select(Job.kind, Job.status, func.count())
        .where(Job.status.in_(("queued", "running")))
        .group_by(Job.kind, Job.status))).all()
    counts = {(kind, status): count for kind, status, count in queue_rows}
    queue = [QueueMetric(kind=kind,
        queued=counts.get((kind, "queued"), 0), running=counts.get((kind, "running"), 0))
        for kind in ("agent", "analyze", "preview", "production")]

    mode = Job.spec["collection_mode"].astext
    duration = func.extract("epoch", Job.finished_at - Job.started_at) * 1000
    collection_rows = (await session.execute(select(
        mode, Job.status, func.count(), func.avg(duration))
        .where(Job.kind == "production", Job.finished_at >= cutoff,
               Job.status.in_(("succeeded", "failed")))
        .group_by(mode, Job.status))).all()
    collection = []
    for current_mode in ("http", "browser"):
        rows = [row for row in collection_rows if row[0] == current_mode]
        succeeded = sum(count for _, status, count, _ in rows if status == "succeeded")
        failed = sum(count for _, status, count, _ in rows if status == "failed")
        durations = [(float(average), count) for _, _, count, average in rows if average is not None]
        duration_total = sum(value * count for value, count in durations)
        duration_count = sum(count for _, count in durations)
        total = succeeded + failed
        collection.append(CollectionMetric(mode=current_mode, succeeded=succeeded, failed=failed,
            success_rate=succeeded / total if total else None,
            average_duration_ms=duration_total / duration_count if duration_count else None))

    active_deliveries = await session.scalar(select(func.count()).select_from(Delivery).where(
        Delivery.status.in_(("queued", "sending", "retrying")))) or 0
    delivery_rows = (await session.execute(select(Delivery.status, func.count())
        .where(Delivery.created_at >= cutoff, Delivery.status.in_(("sent", "failed", "cancelled")))
        .group_by(Delivery.status))).all()
    delivery_counts = dict(delivery_rows)
    sent = delivery_counts.get("sent", 0)
    failed = delivery_counts.get("failed", 0)
    cancelled = delivery_counts.get("cancelled", 0)
    terminal = sent + failed
    deliveries = DeliveryMetric(active=active_deliveries, sent=sent, failed=failed,
        cancelled=cancelled, failure_rate=failed / terminal if terminal else 0.0)

    usage = Job.result["usage"]
    bucket = func.date_trunc("day", Job.created_at)
    usage_rows = (await session.execute(select(
        User.id, User.email, bucket,
        func.coalesce(func.sum(cast(usage["requests"].astext, Integer)), 0),
        func.coalesce(func.sum(cast(usage["input_tokens"].astext, Integer)), 0),
        func.coalesce(func.sum(cast(usage["output_tokens"].astext, Integer)), 0),
        func.coalesce(func.sum(cast(usage["total_tokens"].astext, Integer)), 0))
        .join(User, User.id == Job.user_id)
        .where(Job.kind == "agent", Job.created_at >= cutoff, Job.result.is_not(None))
        .group_by(User.id, User.email, bucket)
        .order_by(bucket.desc(), User.email))).all()
    usage_items = [UsageMetric(user_id=user_id, email=email, bucket=bucket_at,
        requests=requests, input_tokens=input_tokens, output_tokens=output_tokens,
        total_tokens=total_tokens)
        for user_id, email, bucket_at, requests, input_tokens, output_tokens, total_tokens
        in usage_rows]
    return SystemMetrics(generated_at=now, hours=hours, queue=queue, collection=collection,
        deliveries=deliveries, usage=usage_items)
