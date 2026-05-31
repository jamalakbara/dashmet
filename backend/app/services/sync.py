import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.exceptions import ForbiddenError, NotFoundError
from app.models.metrics import SyncJob
from app.services.accounts import assert_account_belongs_to_org

JOB_TTLS = {
    "structure": 30,
    "insights_daily": 15,
    "insights_async": 60,
    "creatives": 60,
    "breakdown": 30,
}

NEXT_RUN_MINUTES = {
    "structure": 30,
    "insights_daily": 15,
    "insights_async": 360,
    "creatives": 60,
    "breakdown": 30,
}


def _is_stale(last_run: Optional[datetime], ttl_minutes: int) -> bool:
    if not last_run:
        return True
    now = datetime.now(timezone.utc)
    last_aware = last_run if last_run.tzinfo else last_run.replace(tzinfo=timezone.utc)
    return (now - last_aware).total_seconds() > ttl_minutes * 60


def get_sync_status(
    db: Session,
    redis_client,
    account_id: str,
    org_id: str,
) -> dict:
    assert_account_belongs_to_org(db, account_id, org_id)
    account_uuid = uuid.UUID(account_id)

    job_types = ["structure", "insights_daily", "insights_async", "creatives", "breakdown"]
    jobs_status = {}
    has_warning = False

    for jt in job_types:
        row = (
            db.query(SyncJob)
            .filter(
                SyncJob.account_id == account_uuid,
                SyncJob.job_type == jt,
            )
            .order_by(SyncJob.created_at.desc())
            .first()
        )

        if row:
            stale = _is_stale(row.completed_at, JOB_TTLS.get(jt, 30))
            next_run = None
            if row.completed_at:
                completed_aware = (
                    row.completed_at
                    if row.completed_at.tzinfo
                    else row.completed_at.replace(tzinfo=timezone.utc)
                )
                next_run = completed_aware + timedelta(minutes=NEXT_RUN_MINUTES.get(jt, 30))

            # Detect stuck jobs: running longer than 3× TTL means the worker died
            effective_status = row.status
            if row.status == "running":
                if not row.started_at:
                    effective_status = "timed_out"
                else:
                    started_aware = (
                        row.started_at if row.started_at.tzinfo
                        else row.started_at.replace(tzinfo=timezone.utc)
                    )
                    elapsed = (datetime.now(timezone.utc) - started_aware).total_seconds()
                    if elapsed > JOB_TTLS.get(jt, 30) * 60 * 2:
                        effective_status = "timed_out"

            jobs_status[jt] = {
                "status": effective_status,
                "last_run_at": row.completed_at,
                "next_run_at": next_run,
                "is_stale": stale,
                "percent_complete": row.rows_written if jt == "insights_async" else None,
            }
            if effective_status in ("failed", "timed_out") or stale:
                has_warning = True
        else:
            jobs_status[jt] = {
                "status": "pending",
                "last_run_at": None,
                "next_run_at": None,
                "is_stale": True,
                "percent_complete": None,
            }
            has_warning = True

    rate_limit = {
        "insights_app_pct": 0.0,
        "insights_acc_pct": 0.0,
        "structure_acc_pct": 0.0,
        "access_tier": "standard_access",
    }
    if redis_client:
        for key in ["insights_app_pct", "insights_acc_pct", "structure_acc_pct"]:
            val = redis_client.get(f"rate_limit:{account_id}:{key}")
            if val:
                rate_limit[key] = float(val)
        tier = redis_client.get(f"rate_limit:{account_id}:access_tier")
        if tier:
            rate_limit["access_tier"] = tier

    return {
        "account_id": account_id,
        "jobs": jobs_status,
        "rate_limit": rate_limit,
        "has_warning": has_warning,
    }


def trigger_sync(
    db: Session,
    account_id: str,
    org_id: str,
    job_types: list[str],
) -> list[str]:
    account = assert_account_belongs_to_org(db, account_id, org_id)
    valid_types = set(JOB_TTLS.keys())
    job_ids = []

    for jt in job_types:
        if jt not in valid_types:
            continue

        job = SyncJob(
            account_id=account.id,
            platform_id=account.platform_id,
            job_type=jt,
            status="pending",
        )
        db.add(job)
        db.flush()
        job_ids.append(str(job.id))

        if jt == "structure":
            from workers.tasks.structure import sync_structure_for_account
            sync_structure_for_account.delay(str(account.id))
        elif jt == "insights_daily":
            from workers.tasks.insights import sync_insights_for_account
            sync_insights_for_account.delay(str(account.id))
        elif jt == "insights_async":
            from workers.tasks.async_jobs import submit_async_job_for_account
            submit_async_job_for_account.delay(str(account.id))

    return job_ids
