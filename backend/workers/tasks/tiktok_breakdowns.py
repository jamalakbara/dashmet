"""
TikTok breakdown sync worker.
Fetches audience demographic breakdowns (age/gender, country, platform, device)
using report_type=AUDIENCE from TikTok's integrated reporting API.
Schedule: every 1 hour via Celery Beat.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from workers.celery_app import celery_app, HEAVY_SOFT_TIME_LIMIT, HEAVY_TIME_LIMIT, LOCK_TTL

logger = logging.getLogger(__name__)

STALE_THRESHOLD = timedelta(hours=1)

BREAKDOWN_METRICS = ["spend", "impressions", "reach", "clicks", "ctr", "cpm", "cpc", "conversion"]

# Maps internal breakdown_type → TikTok dimension + how to extract breakdown_value.
# breakdown_type keys match Meta's so the frontend works without changes.
#
# TikTok API does not support combined age+gender in one query — we use the age
# dimension only and store as "{age}__" so parse_dimensions returns {age, gender:""}
# which renders correctly in the age/gender chart.
#
# TikTok "platform" dimension = OS (IOS/ANDROID), used for the device chart
# (frontend falls back to breakdown_value when r.dimensions.device is absent).
#
# TikTok "placement" dimension = ad placement (PLACEMENT_TIKTOK etc.), stored
# as "{placement}__" to match the publisher_platform__position format.
TIKTOK_BREAKDOWN_CONFIGS = {
    "age_gender": {
        "dimension": ["age", "gender"],
        "value_fn": lambda dims: f"{dims.get('age', '')}__{dims.get('gender', '')}",
    },
    "country": {
        "dimension": "country_code",
        "value_fn": lambda dims: dims.get("country_code", ""),
    },
    "platform_position": {
        "dimension": "placement",
        "value_fn": lambda dims: f"{dims.get('placement', '')}__",
    },
    "device": {
        "dimension": "platform",
        "value_fn": lambda dims: dims.get("platform", ""),
    },
}


def _resolve_dates(date_preset: str, account_timezone: str = "UTC") -> tuple[str, str]:
    """Delegate to the single source of truth used by the API layer so the stored
    breakdown `date` always falls inside the range the /breakdown endpoint queries.
    Returns TikTok-API-formatted date strings (the breakdown row is stored at start)."""
    from app.services.insights import resolve_date_range
    start, end = resolve_date_range(date_preset, account_timezone)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _is_stale(db, account_id: uuid.UUID) -> bool:
    from app.models.metrics import SyncJob
    job = (
        db.query(SyncJob)
        .filter(
            SyncJob.account_id == account_id,
            SyncJob.job_type == "breakdowns",
            SyncJob.status == "completed",
        )
        .order_by(SyncJob.completed_at.desc())
        .first()
    )
    if not job or not job.completed_at:
        return True
    return datetime.now(timezone.utc) - job.completed_at > STALE_THRESHOLD


@celery_app.task(
    name="workers.tasks.tiktok_breakdowns.sync_tiktok_breakdowns_all",
    bind=True,
    max_retries=3,
)
def sync_tiktok_breakdowns_all(self):
    from workers.db_helpers import get_worker_db
    from workers.dispatch import stagger_dispatch
    from app.models.platform import Account

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(Account.account_status == "active", Account.platform_id == "tiktok")
            .all()
        ]
    count = stagger_dispatch(sync_tiktok_breakdowns_for_account, pairs)
    logger.info("Enqueued TikTok breakdown sync for %s accounts", count)


@celery_app.task(
    name="workers.tasks.tiktok_breakdowns.sync_tiktok_breakdowns_for_account",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def sync_tiktok_breakdowns_for_account(self, account_id: str, date_preset: str = "last_30d"):
    from celery.exceptions import SoftTimeLimitExceeded
    from workers.db_helpers import get_worker_db, create_sync_job, finalize_sync_job
    from workers.rate_limit import acquire_lock, release_lock, redis_client
    from app.models.platform import Account, PlatformConnection
    from app.models.metrics import MetricBreakdowns
    from app.services.auth import decrypt_token
    from workers.tiktok_client import TikTokClient, TikTokAPIError

    account_uuid = uuid.UUID(account_id)

    lock_token = acquire_lock("tiktok_breakdowns", account_id, LOCK_TTL)
    if not lock_token:
        logger.info("TikTok breakdowns already running for %s — skip", account_id)
        return

    job_id = create_sync_job(account_uuid, "tiktok", "breakdown")

    try:
        with get_worker_db() as db:
            account = db.get(Account, account_uuid)
            if not account:
                finalize_sync_job(job_id, "skipped")
                return

            if not _is_stale(db, account_uuid):
                finalize_sync_job(job_id, "skipped")
                return

            conn = db.get(PlatformConnection, account.platform_connection_id)
            access_token = decrypt_token(conn.access_token)
            advertiser_id = account.external_id
            account_timezone = account.timezone

        start_date, end_date = _resolve_dates(date_preset, account_timezone)
        total = 0

        with TikTokClient(access_token, redis_client=redis_client) as client:
            for bd_type, cfg in TIKTOK_BREAKDOWN_CONFIGS.items():
                dimension = cfg["dimension"]
                value_fn = cfg["value_fn"]
                extra_dims = dimension if isinstance(dimension, list) else [dimension]

                rows = client.get_report(
                    advertiser_id=advertiser_id,
                    data_level="AUCTION_ADVERTISER",
                    dimensions=["advertiser_id"] + extra_dims,
                    metrics=BREAKDOWN_METRICS,
                    start_date=start_date,
                    end_date=end_date,
                    report_type="AUDIENCE",
                )

                bd_rows = []
                for row in rows:
                    dims = row.get("dimensions", {})
                    mets = row.get("metrics", {})

                    val = value_fn(dims)
                    if not val:
                        continue

                    def _f(key):
                        v = mets.get(key)
                        if v is None or v == "":
                            return None
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            return None

                    bd_rows.append({
                        "entity_type": "account",
                        "entity_id": account_uuid,
                        "platform_id": "tiktok",
                        "account_id": account_uuid,
                        "date": datetime.strptime(start_date, "%Y-%m-%d").date(),
                        "breakdown_type": bd_type,
                        "breakdown_value": val,
                        "impressions": _f("impressions"),
                        "reach": _f("reach"),
                        "clicks": _f("clicks"),
                        "spend": _f("spend"),
                        "conversions": _f("conversion"),
                        "ctr": _f("ctr"),
                        "cpm": _f("cpm"),
                        "cpc": _f("cpc"),
                        "fetched_at": datetime.now(timezone.utc),
                    })

                if bd_rows:
                    with get_worker_db() as db:
                        # This task stores ONE whole-period aggregate per segment, keyed
                        # by the period's start_date — which shifts every day. Without a
                        # purge, each daily run leaves a new dated row and the API's
                        # `date BETWEEN start..end` sums all of them → N× overcount.
                        # Delete the prior aggregate for this account+type before
                        # inserting the fresh one so exactly one set ever exists.
                        # (Delete + insert in one transaction; only runs when we have
                        # fresh rows, so a transient empty/failed fetch never wipes data.)
                        db.execute(
                            MetricBreakdowns.__table__.delete().where(
                                MetricBreakdowns.entity_id == account_uuid,
                                MetricBreakdowns.platform_id == "tiktok",
                                MetricBreakdowns.breakdown_type == bd_type,
                            )
                        )
                        stmt = pg_insert(MetricBreakdowns).values(bd_rows)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["entity_id", "date", "breakdown_type", "breakdown_value"],
                            set_={
                                "impressions": stmt.excluded.impressions,
                                "reach": stmt.excluded.reach,
                                "clicks": stmt.excluded.clicks,
                                "spend": stmt.excluded.spend,
                                "conversions": stmt.excluded.conversions,
                                "ctr": stmt.excluded.ctr,
                                "cpm": stmt.excluded.cpm,
                                "cpc": stmt.excluded.cpc,
                                "fetched_at": stmt.excluded.fetched_at,
                            },
                        )
                        db.execute(stmt)
                    total += len(bd_rows)
                    logger.info("[%s] TikTok breakdown %s: %s rows", account_id, bd_type, len(bd_rows))

        finalize_sync_job(job_id, "completed", rows_written=total)
        logger.info("[%s] TikTok breakdown sync complete: %s rows", account_id, total)

    except SoftTimeLimitExceeded as exc:
        logger.error("TikTok breakdown sync for %s exceeded soft time limit", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        return
    except TikTokAPIError as exc:
        logger.error("TikTok API error for breakdowns %s: %s", account_id, exc)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error in TikTok breakdown sync for %s", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    finally:
        release_lock("tiktok_breakdowns", account_id, lock_token)
