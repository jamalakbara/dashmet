"""
TikTok insights sync worker.
Fetches daily metrics from TikTok's integrated reporting API.
Schedule: every 15 minutes via Celery Beat.
"""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from workers.celery_app import celery_app, HEAVY_SOFT_TIME_LIMIT, HEAVY_TIME_LIMIT, LOCK_TTL

logger = logging.getLogger(__name__)

STALE_THRESHOLD = timedelta(minutes=15)

SCALAR_METRICS = [
    "spend", "impressions", "clicks", "ctr", "cpc", "cpm", "reach", "frequency",
]

ACTION_METRICS = [
    "video_play_actions", "video_watched_2s", "video_watched_6s",
    "video_views_p25", "video_views_p50", "video_views_p75", "video_views_p100",
    "average_video_play", "average_video_play_per_user",
    "conversion", "result",
    "likes", "shares", "comments", "follows", "profile_visits",
    "engagements",
]

# Website/app event metrics are only valid for advertisers with a Pixel / app SDK
# configured — TikTok rejects the WHOLE request with "invalid metric fields" otherwise.
# Requested with a graceful fallback (see sync loop) so they never break core metrics.
EVENT_METRICS = [
    "onsite_shopping", "total_onsite_shopping_value", "onsite_on_web_cart",
    "onsite_initiate_checkout_count",
    "ix_page_view_count", "total_onsite_on_web_cart_value",
    "total_onsite_initiate_checkout_count_value",
    "app_event_install",
    "ix_product_click_count",
    "live_effective_views", "live_product_clicks",
]

TIKTOK_ACTION_MAP = {
    "video_play_actions":   ("video_play_actions",               "video_view"),
    "video_watched_2s":     ("video_watched_2s",                 "video_view"),
    "video_watched_6s":     ("video_watched_6s",                 "video_view"),
    "video_views_p25":      ("video_p25_watched_actions",        "video_view"),
    "video_views_p50":      ("video_p50_watched_actions",        "video_view"),
    "video_views_p75":      ("video_p75_watched_actions",        "video_view"),
    "video_views_p100":     ("video_p100_watched_actions",       "video_view"),
    "average_video_play":   ("average_video_play",               "video_view"),
    "average_video_play_per_user": ("average_video_play_per_user", "video_view"),
    "likes":                ("actions",                          "like"),
    "shares":               ("actions",                          "share"),
    "comments":             ("actions",                          "comment"),
    "follows":              ("actions",                          "follow"),
    "profile_visits":       ("actions",                          "profile_visit"),
    "engagements":          ("engagements",                      "engagement"),
    "result":               ("results",                          "result"),
    "onsite_shopping":                            ("page_events",       "purchase"),
    "total_onsite_shopping_value":                ("page_event_values", "purchase"),
    "onsite_on_web_cart":                         ("page_events",       "add_to_cart"),
    "onsite_initiate_checkout_count":             ("page_events",       "checkout"),
    "ix_page_view_count":                         ("page_events",       "page_view"),
    "total_onsite_on_web_cart_value":             ("page_event_values", "add_to_cart"),
    "total_onsite_initiate_checkout_count_value": ("page_event_values", "checkout"),
    "ix_product_click_count":                     ("ix_product_click_count", "product_click"),
    "live_effective_views":                       ("live_effective_views",   "live_view"),
    "live_product_clicks":                        ("live_product_clicks",    "product_click"),
    "app_event_install":         ("app_events",                  "install"),
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
        "last_90d":    (today - timedelta(90), today - timedelta(1)),
        "this_month":  (today.replace(day=1), today),
        "last_month":  (
            (today.replace(day=1) - timedelta(1)).replace(day=1),
            today.replace(day=1) - timedelta(1),
        ),
    }
    start, end = presets.get(date_preset, (today - timedelta(7), today - timedelta(1)))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# TikTok's reporting API rejects any `stat_time_day` request wider than 30 days
# ("max time span is 30 days when use stat_time_day"). A historical backfill
# (last_90d) must therefore be split into ≤30-day windows and fetched per chunk.
TIKTOK_MAX_REPORT_DAYS = 30


def _date_chunks(start_date: str, end_date: str, max_days: int = TIKTOK_MAX_REPORT_DAYS) -> list[tuple[str, str]]:
    """Split an inclusive [start, end] ISO-date range into contiguous windows of
    at most `max_days` calendar days each (inclusive), oldest first."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    chunks: list[tuple[str, str]] = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        chunks.append((cur.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        cur = chunk_end + timedelta(days=1)
    return chunks


def _is_stale(db, account_id: uuid.UUID, job_type: str = "insights_daily", ttl: timedelta = STALE_THRESHOLD) -> bool:
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
    name="workers.tasks.tiktok_insights.sync_tiktok_insights_daily_all",
    bind=True,
    max_retries=3,
)
def sync_tiktok_insights_daily_all(self):
    from workers.db_helpers import get_worker_db
    from workers.dispatch import stagger_dispatch
    from app.models.platform import Account

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(Account.account_status != "disabled", Account.platform_id == "tiktok")
            .all()
        ]
    count = stagger_dispatch(sync_tiktok_insights_for_account, pairs)
    logger.info("Enqueued TikTok insights sync for %s accounts", count)


@celery_app.task(
    name="workers.tasks.tiktok_insights.sync_tiktok_insights_for_account",
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def sync_tiktok_insights_for_account(self, account_id: str, date_preset: str = "last_7d", job_type: str = "insights_daily"):
    from celery.exceptions import SoftTimeLimitExceeded
    from workers.db_helpers import (
        get_worker_db,
        create_sync_job,
        finalize_sync_job,
        upsert_metrics_daily,
        bulk_upsert_action_stats,
    )
    from workers.rate_limit import acquire_lock, release_lock, redis_client
    from app.models.platform import Account, AccountConfig, PlatformConnection
    from app.models.structure import Campaign, AdGroup, Ad
    from app.services.auth import decrypt_token
    from workers.tiktok_client import TikTokClient, TikTokAPIError

    account_uuid = uuid.UUID(account_id)

    # Early staleness check — avoids acquiring the lock and writing a job row
    # for accounts that don't need a sync yet (every beat cycle, most accounts
    # are still fresh from the previous run).
    historical_ttl = timedelta(hours=6)
    ttl = historical_ttl if job_type == "insights_historical" else STALE_THRESHOLD
    with get_worker_db() as db:
        if not _is_stale(db, account_uuid, job_type, ttl):
            logger.info("TikTok insights (%s) fresh for %s — skip", job_type, account_id)
            return

    # Overlap guard. daily and historical are distinct syncs → distinct lock keys.
    lock_name = f"tiktok_{job_type}"
    lock_token = acquire_lock(lock_name, account_id, LOCK_TTL)
    if not lock_token:
        logger.info("TikTok insights (%s) already running for %s — skip", job_type, account_id)
        return

    job_id = create_sync_job(account_uuid, "tiktok", job_type)

    connection_id = None
    try:
        with get_worker_db() as db:
            account = db.get(Account, account_uuid)
            if not account:
                finalize_sync_job(job_id, "skipped")
                return

            conn = db.get(PlatformConnection, account.platform_connection_id)
            connection_id = str(conn.id) if conn else None
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
        base_metrics = SCALAR_METRICS + ACTION_METRICS
        event_supported = True  # flipped off on the first "invalid metric fields" error

        total_metric_rows = 0
        total_action_rows = 0

        with TikTokClient(access_token, redis_client=redis_client) as client:
            for data_level, entity_type, entity_dim in DATA_LEVELS:
                entity_map = {"campaign_id": camp_map, "adgroup_id": adgroup_map, "ad_id": ad_map}[entity_dim]
                dimensions = [entity_dim, "stat_time_day"]

                # TikTok caps a stat_time_day report at 30 days, so a 90-day
                # historical backfill is fetched as ≤30-day chunks and merged.
                rows = []
                for chunk_start, chunk_end in _date_chunks(start_date, end_date):
                    req_metrics = base_metrics + (EVENT_METRICS if event_supported else [])
                    try:
                        chunk_rows = client.get_report(
                            advertiser_id=advertiser_id,
                            data_level=data_level,
                            dimensions=dimensions,
                            metrics=req_metrics,
                            start_date=chunk_start,
                            end_date=chunk_end,
                        )
                    except TikTokAPIError as e:
                        # Web/app event metrics need a Pixel/app SDK; TikTok 400s the whole
                        # request otherwise. Drop them and retry core-only (persists for the
                        # rest of the run) so the other metrics still sync.
                        if event_supported and "invalid metric" in str(e).lower():
                            logger.info("[%s] TikTok event metrics unsupported — core only", account_id)
                            event_supported = False
                            chunk_rows = client.get_report(
                                advertiser_id=advertiser_id,
                                data_level=data_level,
                                dimensions=dimensions,
                                metrics=base_metrics,
                                start_date=chunk_start,
                                end_date=chunk_end,
                            )
                        else:
                            raise
                    rows.extend(chunk_rows)

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
                        row_date = datetime.strptime(stat_date[:10], "%Y-%m-%d").date()
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
        # Recovery (P-2): a clean run clears any prior token alert for this
        # connection. Helper self-guards on last_error and swallows its own errors.
        if connection_id:
            from workers.token_alerts import clear_connection_token_failure
            clear_connection_token_failure(connection_id)
        logger.info(
            "TikTok insights sync done for account %s — %s metric rows, %s action rows",
            account_id, total_metric_rows, total_action_rows,
        )

    except SoftTimeLimitExceeded as exc:
        logger.error("TikTok insights sync for %s exceeded soft time limit", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        return
    except TikTokAPIError as exc:
        if exc.is_auth and connection_id:
            from workers.token_alerts import alert_connection_token_failure
            alert_connection_token_failure(
                connection_id, platform_label="TikTok", detail=str(exc)
            )
        logger.error("TikTok API error for insights %s: %s", account_id, exc)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error in TikTok insights sync for %s", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    finally:
        release_lock(lock_name, account_id, lock_token)
