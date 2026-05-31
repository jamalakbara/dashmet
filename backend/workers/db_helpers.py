"""
DB upsert helpers for the sync workers.
Uses PostgreSQL-specific INSERT ... ON CONFLICT DO UPDATE with COALESCE.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.metrics import MetricActionStats, MetricsDaily

NULLABLE_METRIC_COLUMNS = [
    "impressions", "reach", "frequency", "clicks", "spend",
    "ctr", "cpm", "cpc", "cpp",
    "unique_clicks", "inline_link_clicks", "unique_inline_link_clicks",
    "inline_link_click_ctr", "unique_ctr",
    "cost_per_inline_link_click", "cost_per_unique_click",
    "inline_post_engagement", "cost_per_inline_post_engagement",
    "auction_bid", "auction_competitiveness", "auction_max_competitor_bid",
    "total_actions", "total_unique_actions", "result_rate",
    "estimated_ad_recall_rate", "estimated_ad_recallers",
    "attribution_window",
]


@contextmanager
def get_worker_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_sync_job(account_id: uuid.UUID, platform_id: str, job_type: str) -> uuid.UUID:
    """Commit a 'running' SyncJob immediately in its own transaction. Returns job.id."""
    from app.models.metrics import SyncJob
    with get_worker_db() as db:
        job = SyncJob(
            account_id=account_id,
            platform_id=platform_id,
            job_type=job_type,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.flush()
        return job.id


def _sanitize_error(error: Exception) -> str:
    """Strip access_token query param from URLs that appear in error messages."""
    import re
    msg = str(error)[:4000]
    msg = re.sub(r"access_token=[^&'\"\s]+", "access_token=<redacted>", msg)
    return msg[:2000]


def finalize_sync_job(
    job_id: uuid.UUID,
    status: str,
    rows_written: Optional[int] = None,
    error: Optional[Exception] = None,
) -> None:
    """Update job status in its own committed transaction — survives data rollbacks."""
    from app.models.metrics import SyncJob
    with get_worker_db() as db:
        job = db.get(SyncJob, job_id)
        if not job:
            return
        job.status = status
        job.completed_at = datetime.now(timezone.utc)
        if rows_written is not None:
            job.rows_written = rows_written
        if error is not None:
            job.error_message = _sanitize_error(error)


def upsert_metrics_daily(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0

    now = datetime.now(timezone.utc)
    for row in rows:
        row.setdefault("fetched_at", now)
        row.setdefault("is_estimated", False)

    present_cols = set().union(*(row.keys() for row in rows))
    for row in rows:
        for col in present_cols:
            row.setdefault(col, None)

    stmt = pg_insert(MetricsDaily).values(rows)
    update_dict = {
        "fetched_at": stmt.excluded.fetched_at,
        "is_estimated": stmt.excluded.is_estimated,
    }
    for col in NULLABLE_METRIC_COLUMNS:
        if col not in present_cols:
            continue
        tbl_col = MetricsDaily.__table__.c.get(col)
        exc_col = getattr(stmt.excluded, col, None)
        if tbl_col is not None and exc_col is not None:
            from sqlalchemy import func
            update_dict[col] = func.coalesce(exc_col, tbl_col)

    stmt = stmt.on_conflict_do_update(
        index_elements=["entity_type", "entity_id", "date"],
        set_=update_dict,
    )
    result = db.execute(stmt)
    return result.rowcount


def bulk_upsert_action_stats(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0

    now = datetime.now(timezone.utc)
    for row in rows:
        row.setdefault("fetched_at", now)

    stmt = pg_insert(MetricActionStats).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["entity_id", "date", "field_name", "action_type"],
        set_={
            "value": stmt.excluded.value,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    result = db.execute(stmt)
    return result.rowcount
