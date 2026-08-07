"""
Sync worker — Async Insights Jobs
Handles heavy Meta queries (90d, lifetime) via async job submit → poll → fetch.
"""
import logging
import uuid
from datetime import datetime, timezone

from workers.celery_app import celery_app, HEAVY_SOFT_TIME_LIMIT, HEAVY_TIME_LIMIT

logger = logging.getLogger(__name__)

ASYNC_FIELDS = ",".join([
    "campaign_id", "campaign_name",
    "impressions", "reach", "clicks", "spend", "ctr", "cpm", "cpc", "cpp",
    "frequency", "inline_link_clicks",
    "inline_post_engagement", "cost_per_inline_post_engagement",
    "estimated_ad_recall_rate", "estimated_ad_recallers",
    "actions", "action_values", "cost_per_action_type",
    "purchase_roas",
    "video_play_actions", "video_continuous_2_sec_watched_actions",
    "video_p25_watched_actions",
    "video_p50_watched_actions", "video_p75_watched_actions",
    "video_p100_watched_actions", "video_thruplay_watched_actions",
    "date_start", "date_stop",
])


@celery_app.task(
    name="workers.tasks.async_jobs.submit_async_jobs",
    bind=True,
    max_retries=3,
)
def submit_async_jobs(self, date_preset: str = "last_90d"):
    from workers.db_helpers import get_worker_db
    from workers.dispatch import stagger_dispatch
    from app.models.platform import Account

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(Account.account_status == "active")
            .all()
        ]
    # Wider spread — async submit is a 6h cadence, no need to cluster.
    count = stagger_dispatch(submit_async_job_for_account, pairs, extra_args=(date_preset,), spread_seconds=1800)
    logger.info(f"Submitted async jobs for {count} accounts")


@celery_app.task(
    name="workers.tasks.async_jobs.submit_async_job_for_account",
    bind=True,
    max_retries=3,
    retry_backoff=True,
)
def submit_async_job_for_account(self, account_id: str, date_preset: str = "last_90d"):
    from workers.db_helpers import get_worker_db, create_sync_job, finalize_sync_job
    from workers.meta_client import MetaClient, MetaAPIError
    from workers.rate_limit import (
        apply_backoff, RateLimitBackoff, connection_paused_remaining,
        pause_connection, is_meta_rate_limit_error, HARD_PAUSE_SECONDS,
    )
    from app.models.platform import Account, PlatformConnection
    from app.models.metrics import SyncJob
    from app.services.auth import decrypt_token

    # Phase 1: reads + deduplicate check
    with get_worker_db() as db:
        running = (
            db.query(SyncJob)
            .filter(
                SyncJob.account_id == uuid.UUID(account_id),
                SyncJob.job_type == "insights_async",
                SyncJob.status.in_(["pending", "running"]),
            )
            .first()
        )
        if running:
            logger.info(f"[{account_id}] Async job already running/pending — skip")
            return

        from datetime import timedelta
        last_completed = (
            db.query(SyncJob)
            .filter(
                SyncJob.account_id == uuid.UUID(account_id),
                SyncJob.job_type == "insights_async",
                SyncJob.status == "completed",
            )
            .order_by(SyncJob.completed_at.desc())
            .first()
        )
        if last_completed and last_completed.completed_at:
            completed = last_completed.completed_at
            if not completed.tzinfo:
                completed = completed.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - completed) < timedelta(hours=6):
                logger.info(f"[{account_id}] Async job fresh — skip")
                return

        account = db.get(Account, uuid.UUID(account_id))
        if not account:
            return

        conn = db.get(PlatformConnection, account.platform_connection_id)
        if not conn or not conn.is_active:
            return

        account_id_obj = account.id
        platform_id = account.platform_id
        connection_id = str(conn.id)
        token = decrypt_token(conn.access_token)
        ext_id = account.external_id.replace("act_", "")
        account_tz = account.timezone

    # Gate: skip the whole token while it's rate-limit paused (shared app quota)
    paused = connection_paused_remaining(connection_id)
    if paused > 0:
        logger.info(f"[{account_id}] Connection paused {paused}s — rescheduling async submit")
        self.apply_async(args=[account_id, date_preset], countdown=paused)
        return

    # Phase 2: commit "running" job before Meta API call
    job_id = create_sync_job(account_id_obj, platform_id, "insights_async")

    try:
        apply_backoff(account_id, connection_id)
        # Resolve preset → explicit time_range in the account tz (§2.3): same
        # resolver as the read path, so the async report days == queried days.
        from workers.date_range import meta_time_range
        client = MetaClient(token)
        report_run_id = client.post_async_job(
            ext_id,
            {
                "fields": ASYNC_FIELDS,
                "level": "campaign",
                "time_range": meta_time_range(date_preset, account_tz),
                "time_increment": "1",
            },
        )
        # Store the Meta report_run_id on the job so poll_async_jobs can find it
        with get_worker_db() as db:
            job = db.get(SyncJob, job_id)
            if job:
                job.platform_job_id = report_run_id
        logger.info(f"[{account_id}] Async job submitted: {report_run_id}")
    except RateLimitBackoff as b:
        finalize_sync_job(job_id, "skipped")
        logger.info(f"[{account_id}] Async submit rescheduled in {b.countdown}s ({b.scope})")
        self.apply_async(args=[account_id, date_preset], countdown=b.countdown)
        return
    except MetaAPIError as e:
        if is_meta_rate_limit_error(e.code, e.subcode):
            pause_connection(connection_id, HARD_PAUSE_SECONDS)
            finalize_sync_job(job_id, "skipped")
            logger.warning(f"[{account_id}] Async submit Meta rate-limit (code {e.code}) — pausing connection {HARD_PAUSE_SECONDS}s")
            self.apply_async(args=[account_id, date_preset], countdown=HARD_PAUSE_SECONDS)
            return
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Async submit failed: {e}")
        raise self.retry(exc=e)
    except Exception as e:
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Async submit failed: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    name="workers.tasks.async_jobs.poll_async_jobs",
    bind=True,
)
def poll_async_jobs(self):
    from workers.db_helpers import get_worker_db
    from workers.meta_client import MetaClient
    from app.models.platform import Account, PlatformConnection
    from app.models.metrics import SyncJob
    from app.services.auth import decrypt_token

    with get_worker_db() as db:
        running_jobs = (
            db.query(SyncJob)
            .filter(
                SyncJob.job_type == "insights_async",
                SyncJob.status == "running",
                SyncJob.platform_job_id.isnot(None),
            )
            .all()
        )

        for job in running_jobs:
            account = db.get(Account, job.account_id)
            if not account:
                continue
            conn = db.get(PlatformConnection, account.platform_connection_id)
            if not conn:
                continue

            try:
                token = decrypt_token(conn.access_token)
                client = MetaClient(token)
                data, _ = client.get(f"/{job.platform_job_id}")
                async_status = data.get("async_status", "")
                pct = data.get("async_percent_completion", 0)
                job.rows_written = pct

                logger.info(f"Async job {job.platform_job_id}: {async_status} ({pct}%)")

                if async_status == "Job Completed":
                    fetch_async_results.delay(str(job.id), job.platform_job_id)
                elif async_status in ("Job Failed", "Job Skipped"):
                    job.status = "failed"
                    job.error_message = f"Meta async job status: {async_status}"
                    job.completed_at = datetime.now(timezone.utc)
                    submit_async_job_for_account.delay(str(job.account_id))

            except Exception as e:
                logger.error(f"Poll error for job {job.platform_job_id}: {e}")


@celery_app.task(
    name="workers.tasks.async_jobs.fetch_async_results",
    bind=True,
    max_retries=3,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def fetch_async_results(self, job_id: str, report_run_id: str):
    from workers.db_helpers import (
        get_worker_db, upsert_metrics_daily, bulk_upsert_action_stats,
        finalize_sync_job,
    )
    from workers.meta_client import MetaClient
    from app.models.platform import Account, PlatformConnection
    from app.models.structure import Campaign
    from app.models.metrics import SyncJob
    from app.services.auth import decrypt_token
    from workers.tasks.insights import parse_insight_row, SCALAR_TO_DB

    # Phase 1: reads only
    with get_worker_db() as db:
        job = db.get(SyncJob, uuid.UUID(job_id))
        if not job:
            return

        account = db.get(Account, job.account_id)
        conn = db.get(PlatformConnection, account.platform_connection_id)
        account_id_obj = account.id
        platform_id = account.platform_id
        token = decrypt_token(conn.access_token)

        camp_map = {
            c.platform_campaign_id: c.id
            for c in db.query(Campaign).filter(Campaign.account_id == account.id).all()
        }

    job_uuid = uuid.UUID(job_id)
    try:
        client = MetaClient(token)
        rows = client.paginate(f"/{report_run_id}/insights", {"limit": 200})

        metric_rows = []
        action_rows = []
        for raw in rows:
            platform_campaign_id = raw.get("campaign_id")
            entity_id = camp_map.get(platform_campaign_id)
            if not entity_id:
                continue
            date_str = raw.get("date_start")
            if not date_str:
                continue

            scalars, actions = parse_insight_row("campaign", str(entity_id), date_str, raw)
            scalars.update({
                "entity_type": "campaign",
                "entity_id": entity_id,
                "platform_id": platform_id,
                "account_id": account_id_obj,
                "date": date_str,
            })
            for k in list(scalars.keys()):
                if k not in SCALAR_TO_DB and k not in {
                    "entity_type", "entity_id", "platform_id", "account_id", "date",
                    "fetched_at", "is_estimated", "attribution_window",
                }:
                    del scalars[k]
            metric_rows.append(scalars)

            for a in actions:
                a["entity_id"] = entity_id
                a["account_id"] = account_id_obj
                a["platform_id"] = platform_id
            action_rows.extend(actions)

        with get_worker_db() as db:
            total = upsert_metrics_daily(db, metric_rows)
            total += bulk_upsert_action_stats(db, action_rows)

        finalize_sync_job(job_uuid, "completed", rows_written=total)
        logger.info(f"Async results fetched: {total} rows for job {report_run_id}")

    except Exception as e:
        finalize_sync_job(job_uuid, "failed", error=e)
        logger.error(f"Fetch async results failed for {report_run_id}: {e}")
        raise self.retry(exc=e)
