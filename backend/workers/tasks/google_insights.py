"""
Google Ads insights sync worker.
Fetches daily metrics per entity level via GAQL and writes the normalized
metrics_daily + metric_action_stats tables (same shape as Meta/TikTok). One GAQL
query per level covers core + conversion metrics — Google returns conversions as
scalars (no per-action row multiplication unless segmented), so no second call.
Schedule: every 15 minutes via Celery Beat.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from workers.celery_app import celery_app, HEAVY_SOFT_TIME_LIMIT, HEAVY_TIME_LIMIT, LOCK_TTL

logger = logging.getLogger(__name__)

STALE_THRESHOLD = timedelta(minutes=15)

# (GAQL resource, internal entity_type, GAQL id field path)
DATA_LEVELS = [
    ("campaign", "campaign", "campaign.id"),
    ("ad_group", "adgroup", "ad_group.id"),
    ("ad_group_ad", "ad", "ad_group_ad.ad.id"),
]

# Quartile rate field → internal action field_name (count = rate * impressions).
VIDEO_QUARTILE_FIELDS = {
    "metrics.video_quartile_p25_rate": "video_p25_watched_actions",
    "metrics.video_quartile_p50_rate": "video_p50_watched_actions",
    "metrics.video_quartile_p75_rate": "video_p75_watched_actions",
    "metrics.video_quartile_p100_rate": "video_p100_watched_actions",
}

_CORE_METRIC_FIELDS = (
    "metrics.impressions, metrics.clicks, metrics.cost_micros, "
    "metrics.ctr, metrics.average_cpc, metrics.average_cpm, "
    "metrics.conversions, metrics.conversions_value, metrics.video_views, "
    "metrics.video_quartile_p25_rate, metrics.video_quartile_p50_rate, "
    "metrics.video_quartile_p75_rate, metrics.video_quartile_p100_rate"
)


def _f(raw: dict, key: str) -> float | None:
    val = raw.get(key)
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_google_report_row(
    entity_type: str,
    entity_id: uuid.UUID,
    account_uuid: uuid.UUID,
    row_date,
    raw: dict,
    primary_conversion_action: str = "purchase",
    roas_action_type: str = "purchase",
) -> tuple[dict, list[dict]]:
    """Map one flattened GAQL row → (metrics_daily scalar dict, action_stats rows).
    cost/cpc/cpm are micros (÷1e6); ctr is a ratio (×100 to match Meta's percent)."""
    cost = _f(raw, "metrics.cost_micros")
    cpc = _f(raw, "metrics.average_cpc")
    cpm = _f(raw, "metrics.average_cpm")
    ctr = _f(raw, "metrics.ctr")
    impressions = _f(raw, "metrics.impressions")

    scalars = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "platform_id": "google_ads",
        "account_id": account_uuid,
        "date": row_date,
        "impressions": impressions,
        "clicks": _f(raw, "metrics.clicks"),
        "spend": cost / 1_000_000 if cost is not None else None,
        "cpc": cpc / 1_000_000 if cpc is not None else None,
        "cpm": cpm / 1_000_000 if cpm is not None else None,
        "ctr": ctr * 100 if ctr is not None else None,
    }

    action_rows: list[dict] = []

    def _add(field_name: str, action_type: str, value: float | None):
        if value is None:
            return
        action_rows.append({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "platform_id": "google_ads",
            "account_id": account_uuid,
            "date": row_date,
            "field_name": field_name,
            "action_type": action_type,
            "value": Decimal(str(value)),
        })

    # Conversions + value mapped onto the same action_type the ROAS/CPA join uses.
    _add("conversions", primary_conversion_action, _f(raw, "metrics.conversions"))
    _add("action_values", roas_action_type, _f(raw, "metrics.conversions_value"))

    # Video stages (shared field_name/action_type with Meta/TikTok).
    _add("video_play_actions", "video_view", _f(raw, "metrics.video_views"))
    if impressions:
        for rate_field, internal_field in VIDEO_QUARTILE_FIELDS.items():
            rate = _f(raw, rate_field)
            if rate is not None:
                _add(internal_field, "video_view", round(rate * impressions))

    return scalars, action_rows


def _is_stale(db, account_id: uuid.UUID, job_type: str, ttl: timedelta) -> bool:
    from app.models.metrics import SyncJob
    job = (
        db.query(SyncJob)
        .filter(
            SyncJob.account_id == account_id,
            SyncJob.job_type == job_type,
            SyncJob.status == "completed",
        )
        .order_by(SyncJob.completed_at.desc())
        .first()
    )
    if not job or not job.completed_at:
        return True
    return datetime.now(timezone.utc) - job.completed_at > ttl


@celery_app.task(
    name="workers.tasks.google_insights.sync_google_insights_daily_all",
    bind=True,
    max_retries=3,
)
def sync_google_insights_daily_all(self):
    from workers.db_helpers import get_worker_db
    from workers.dispatch import stagger_dispatch
    from app.models.platform import Account

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(Account.account_status == "active", Account.platform_id == "google_ads")
            .all()
        ]
    count = stagger_dispatch(sync_google_insights_for_account, pairs)
    logger.info("Enqueued Google insights sync for %s accounts", count)


@celery_app.task(
    name="workers.tasks.google_insights.sync_google_insights_for_account",
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def sync_google_insights_for_account(self, account_id: str, date_preset: str = "last_7d", job_type: str = "insights_daily"):
    from celery.exceptions import SoftTimeLimitExceeded
    from workers.db_helpers import (
        get_worker_db,
        create_sync_job,
        finalize_sync_job,
        upsert_metrics_daily,
        bulk_upsert_action_stats,
    )
    from workers.rate_limit import acquire_lock, release_lock, pause_connection
    from app.models.platform import Account, AccountConfig, PlatformConnection
    from app.models.structure import Campaign, AdGroup, Ad
    from app.services.auth import decrypt_token
    from app.services.insights import resolve_date_range
    from workers.google_client import GoogleClient, GoogleAdsClientError

    account_uuid = uuid.UUID(account_id)

    lock_name = f"google_{job_type}"
    lock_token = acquire_lock(lock_name, account_id, LOCK_TTL)
    if not lock_token:
        logger.info("Google insights (%s) already running for %s — skip", job_type, account_id)
        return

    ttl = timedelta(hours=6) if job_type == "insights_historical" else STALE_THRESHOLD
    job_id = create_sync_job(account_uuid, "google_ads", job_type)
    connection_id = None

    try:
        with get_worker_db() as db:
            account = db.get(Account, account_uuid)
            if not account:
                finalize_sync_job(job_id, "skipped")
                return

            if not _is_stale(db, account_uuid, job_type, ttl):
                finalize_sync_job(job_id, "skipped")
                return

            conn = db.get(PlatformConnection, account.platform_connection_id)
            connection_id = str(conn.id)
            refresh_token = decrypt_token(conn.refresh_token)
            customer_id = account.external_id
            account_timezone = account.timezone

            config = (
                db.query(AccountConfig)
                .filter(AccountConfig.account_id == account_uuid)
                .first()
            )
            primary_conversion_action = (config.primary_conversion_action if config else "purchase") or "purchase"
            roas_action_type = (config.roas_action_type if config else "purchase") or "purchase"

            camp_map = {r.platform_campaign_id: r.id for r in db.query(Campaign).filter(Campaign.account_id == account_uuid).all()}
            adgroup_map = {r.platform_adgroup_id: r.id for r in db.query(AdGroup).filter(AdGroup.account_id == account_uuid).all()}
            ad_map = {r.platform_ad_id: r.id for r in db.query(Ad).filter(Ad.account_id == account_uuid).all()}

        start, end = resolve_date_range(date_preset, account_timezone)
        start_str, end_str = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

        total_metric_rows = 0
        total_action_rows = 0

        with GoogleClient(refresh_token) as client:
            for resource, entity_type, id_field in DATA_LEVELS:
                entity_map = {"campaign": camp_map, "adgroup": adgroup_map, "ad": ad_map}[entity_type]
                query = (
                    f"SELECT {id_field}, segments.date, {_CORE_METRIC_FIELDS} "
                    f"FROM {resource} "
                    f"WHERE segments.date BETWEEN '{start_str}' AND '{end_str}'"
                )
                rows = client.search(customer_id, query)

                metric_rows: list[dict] = []
                action_rows: list[dict] = []

                for raw in rows:
                    platform_entity_id = str(raw.get(id_field, ""))
                    entity_id = entity_map.get(platform_entity_id)
                    if not entity_id:
                        continue
                    stat_date = raw.get("segments.date", "")
                    if not stat_date:
                        continue
                    try:
                        row_date = datetime.strptime(stat_date[:10], "%Y-%m-%d").date()
                    except ValueError:
                        continue

                    scalars, actions = parse_google_report_row(
                        entity_type, entity_id, account_uuid, row_date, raw,
                        primary_conversion_action, roas_action_type,
                    )
                    metric_rows.append(scalars)
                    action_rows.extend(actions)

                with get_worker_db() as db:
                    total_metric_rows += upsert_metrics_daily(db, metric_rows)
                    total_action_rows += bulk_upsert_action_stats(db, action_rows)

        finalize_sync_job(job_id, "completed", rows_written=total_metric_rows + total_action_rows)
        logger.info(
            "Google insights sync done for account %s — %s metric rows, %s action rows",
            account_id, total_metric_rows, total_action_rows,
        )

    except SoftTimeLimitExceeded as exc:
        logger.error("Google insights sync for %s exceeded soft time limit", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        return
    except GoogleAdsClientError as exc:
        if exc.is_quota:
            if connection_id:
                pause_connection(connection_id, 300)
            logger.warning("Google quota hit for %s — rescheduling insights in 300s", account_id)
            finalize_sync_job(job_id, "skipped")
            self.apply_async(args=[account_id, date_preset, job_type], countdown=300)
            return
        logger.error("Google API error for insights %s: %s", account_id, exc)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error in Google insights sync for %s", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    finally:
        release_lock(lock_name, account_id, lock_token)
