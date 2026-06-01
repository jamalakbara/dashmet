"""
TikTok insights sync worker.
Fetches daily metrics from TikTok's integrated reporting API.
Schedule: every 15 minutes via Celery Beat.
"""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

STALE_THRESHOLD = timedelta(minutes=15)

SCALAR_METRICS = [
    "spend", "impressions", "clicks", "ctr", "cpc", "cpm", "reach", "frequency",
]

ACTION_METRICS = [
    "video_play_actions", "video_watched_2s", "video_watched_6s",
    "video_views_p25", "video_views_p50", "video_views_p75", "video_views_p100",
    "conversion", "likes", "shares", "comments",
]

TIKTOK_ACTION_MAP = {
    "video_play_actions":  ("video_play_actions",         "video_view"),
    "video_watched_2s":    ("video_watched_2s",           "video_view"),
    "video_watched_6s":    ("video_watched_6s",           "video_view"),
    "video_views_p25":     ("video_p25_watched_actions",  "video_view"),
    "video_views_p50":     ("video_p50_watched_actions",  "video_view"),
    "video_views_p75":     ("video_p75_watched_actions",  "video_view"),
    "video_views_p100":    ("video_p100_watched_actions", "video_view"),
    "likes":               ("actions",                    "like"),
    "shares":              ("actions",                    "share"),
    "comments":            ("actions",                    "comment"),
}

DATA_LEVELS = [
    ("AUCTION_CAMPAIGN", "campaign",  "campaign_id"),
    ("AUCTION_ADGROUP",  "adgroup",   "adgroup_id"),
    ("AUCTION_AD",       "ad",        "ad_id"),
]


def _resolve_dates(date_preset: str) -> tuple[str, str]:
    today = date.today()
    presets = {
        "today":       (today, today),
        "yesterday":   (today - timedelta(1), today - timedelta(1)),
        "last_7d":     (today - timedelta(7), today - timedelta(1)),
        "last_14d":    (today - timedelta(14), today - timedelta(1)),
        "last_30d":    (today - timedelta(30), today - timedelta(1)),
        "this_month":  (today.replace(day=1), today),
        "last_month":  (
            (today.replace(day=1) - timedelta(1)).replace(day=1),
            today.replace(day=1) - timedelta(1),
        ),
    }
    start, end = presets.get(date_preset, (today - timedelta(7), today - timedelta(1)))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _is_stale(db, account_id: uuid.UUID) -> bool:
    from app.models.metrics import SyncJob
    job = (
        db.query(SyncJob)
        .filter(
            SyncJob.account_id == account_id,
            SyncJob.job_type == "insights_daily",
            SyncJob.status == "completed",
        )
        .order_by(SyncJob.completed_at.desc())
        .first()
    )
    if not job or not job.completed_at:
        return True
    return datetime.now(timezone.utc) - job.completed_at > STALE_THRESHOLD


@celery_app.task(
    name="workers.tasks.tiktok_insights.sync_tiktok_insights_daily_all",
    bind=True,
    max_retries=3,
)
def sync_tiktok_insights_daily_all(self):
    from workers.db_helpers import get_worker_db
    from app.models.platform import Account

    with get_worker_db() as db:
        accounts = (
            db.query(Account)
            .filter(Account.account_status == "active", Account.platform_id == "tiktok")
            .all()
        )
        for account in accounts:
            sync_tiktok_insights_for_account.delay(str(account.id))
        logger.info("Enqueued TikTok insights sync for %s accounts", len(accounts))


@celery_app.task(
    name="workers.tasks.tiktok_insights.sync_tiktok_insights_for_account",
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def sync_tiktok_insights_for_account(self, account_id: str, date_preset: str = "last_7d"):
    from workers.db_helpers import (
        get_worker_db,
        create_sync_job,
        finalize_sync_job,
        upsert_metrics_daily,
        bulk_upsert_action_stats,
    )
    from app.models.platform import Account, AccountConfig, PlatformConnection
    from app.models.structure import Campaign, AdGroup, Ad
    from app.services.auth import decrypt_token
    from workers.tiktok_client import TikTokClient, TikTokAPIError

    account_uuid = uuid.UUID(account_id)
    job_id = create_sync_job(account_uuid, "tiktok", "insights_daily")

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

            config = (
                db.query(AccountConfig)
                .filter(AccountConfig.account_id == account_uuid)
                .first()
            )
            primary_conversion_action = (
                config.primary_conversion_action if config else "purchase"
            ) or "purchase"

            # Build platform_id → internal entity UUID maps
            camp_map: dict[str, uuid.UUID] = {
                row.platform_campaign_id: row.id
                for row in db.query(Campaign).filter(Campaign.account_id == account_uuid).all()
            }
            adgroup_map: dict[str, uuid.UUID] = {
                row.platform_adgroup_id: row.id
                for row in db.query(AdGroup).filter(AdGroup.account_id == account_uuid).all()
            }
            ad_map: dict[str, uuid.UUID] = {
                row.platform_ad_id: row.id
                for row in db.query(Ad).filter(Ad.account_id == account_uuid).all()
            }

        start_date, end_date = _resolve_dates(date_preset)
        all_metrics = SCALAR_METRICS + ACTION_METRICS

        total_metric_rows = 0
        total_action_rows = 0

        with TikTokClient(access_token) as client:
            for data_level, entity_type, entity_dim in DATA_LEVELS:
                entity_map = {"campaign_id": camp_map, "adgroup_id": adgroup_map, "ad_id": ad_map}[entity_dim]
                dimensions = [entity_dim, "stat_time_day"]

                rows = client.get_report(
                    advertiser_id=advertiser_id,
                    data_level=data_level,
                    dimensions=dimensions,
                    metrics=all_metrics,
                    start_date=start_date,
                    end_date=end_date,
                )

                metric_rows: list[dict] = []
                action_rows: list[dict] = []

                for row in rows:
                    dims = row.get("dimensions", {})
                    mets = row.get("metrics", {})

                    platform_entity_id = str(dims.get(entity_dim, ""))
                    entity_id = entity_map.get(platform_entity_id)
                    if not entity_id:
                        continue

                    stat_date = dims.get("stat_time_day", "")
                    if not stat_date:
                        continue

                    try:
                        row_date = datetime.strptime(stat_date, "%Y-%m-%d").date()
                    except ValueError:
                        continue

                    def _f(key: str) -> float | None:
                        val = mets.get(key)
                        if val is None or val == "":
                            return None
                        try:
                            return float(val)
                        except (TypeError, ValueError):
                            return None

                    metric_rows.append({
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "platform_id": "tiktok",
                        "account_id": account_uuid,
                        "date": row_date,
                        "spend": _f("spend"),
                        "impressions": _f("impressions"),
                        "clicks": _f("clicks"),
                        "ctr": _f("ctr"),
                        "cpc": _f("cpc"),
                        "cpm": _f("cpm"),
                        "reach": _f("reach"),
                        "frequency": _f("frequency"),
                    })

                    for tiktok_key, (field_name, action_type) in TIKTOK_ACTION_MAP.items():
                        val = _f(tiktok_key)
                        if val is not None:
                            action_rows.append({
                                "entity_type": entity_type,
                                "entity_id": entity_id,
                                "platform_id": "tiktok",
                                "account_id": account_uuid,
                                "date": row_date,
                                "field_name": field_name,
                                "action_type": action_type,
                                "value": Decimal(str(val)),
                            })

                    conv_val = _f("conversion")
                    if conv_val is not None:
                        action_rows.append({
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "platform_id": "tiktok",
                            "account_id": account_uuid,
                            "date": row_date,
                            "field_name": "conversions",
                            "action_type": primary_conversion_action,
                            "value": Decimal(str(conv_val)),
                        })

                with get_worker_db() as db:
                    total_metric_rows += upsert_metrics_daily(db, metric_rows)
                    total_action_rows += bulk_upsert_action_stats(db, action_rows)

        total_rows = total_metric_rows + total_action_rows
        finalize_sync_job(job_id, "completed", rows_written=total_rows)
        logger.info(
            "TikTok insights sync done for account %s — %s metric rows, %s action rows",
            account_id, total_metric_rows, total_action_rows,
        )

    except TikTokAPIError as exc:
        logger.error("TikTok API error for insights %s: %s", account_id, exc)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error in TikTok insights sync for %s", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
