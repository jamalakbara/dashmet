"""
Sync worker — Insights (daily metrics)
Fetches scalar + action metrics from Meta Insights API and upserts into DB.
Schedule: every 15 minutes via Celery Beat.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_METRIC_FIELDS = ",".join([
    "impressions", "clicks", "spend", "ctr", "cpm", "cpc", "cpp",
    "frequency", "inline_link_clicks", "inline_link_click_ctr",
    "cost_per_inline_link_click",
    "outbound_clicks", "outbound_clicks_ctr", "cost_per_outbound_click",
    "actions", "action_values", "cost_per_action_type",
    "purchase_roas", "website_purchase_roas",
    "video_play_actions", "video_avg_time_watched_actions",
    "video_p25_watched_actions", "video_p50_watched_actions",
    "video_p75_watched_actions", "video_p100_watched_actions",
    "video_thruplay_watched_actions",
    "date_start", "date_stop",
])

NON_UNIQUE_FIELDS = f"campaign_id,campaign_name,{_METRIC_FIELDS}"
ADGROUP_NON_UNIQUE_FIELDS = f"adset_id,adset_name,{_METRIC_FIELDS}"
AD_NON_UNIQUE_FIELDS = f"ad_id,ad_name,{_METRIC_FIELDS}"

UNIQUE_FIELDS = "campaign_id,reach,unique_clicks,unique_inline_link_clicks,unique_ctr,date_start,date_stop"
ADGROUP_UNIQUE_FIELDS = "adset_id,reach,unique_clicks,unique_inline_link_clicks,unique_ctr,date_start,date_stop"
AD_UNIQUE_FIELDS = "ad_id,reach,unique_clicks,unique_inline_link_clicks,unique_ctr,date_start,date_stop"

ACTION_STAT_FIELDS = {
    "actions", "action_values", "unique_actions",
    "cost_per_action_type", "cost_per_unique_action_type",
    "conversions", "conversion_values", "cost_per_conversion",
    "purchase_roas", "website_purchase_roas", "mobile_app_purchase_roas",
    "outbound_clicks", "unique_outbound_clicks", "outbound_clicks_ctr", "cost_per_outbound_click",
    "video_play_actions", "video_avg_time_watched_actions",
    "video_continuous_2_sec_watched_actions", "video_thruplay_watched_actions",
    "video_p25_watched_actions", "video_p50_watched_actions",
    "video_p75_watched_actions", "video_p100_watched_actions",
    "results", "cost_per_result",
}

SKIP_FIELDS = {
    "campaign_id", "campaign_name", "adset_id", "adset_name",
    "ad_id", "ad_name", "date_start", "date_stop",
    "account_id", "account_name", "account_currency",
}

SCALAR_TO_DB = {
    "impressions": "impressions",
    "clicks": "clicks",
    "spend": "spend",
    "ctr": "ctr",
    "cpm": "cpm",
    "cpc": "cpc",
    "cpp": "cpp",
    "frequency": "frequency",
    "inline_link_clicks": "inline_link_clicks",
    "inline_link_click_ctr": "inline_link_click_ctr",
    "cost_per_inline_link_click": "cost_per_inline_link_click",
    "reach": "reach",
    "unique_clicks": "unique_clicks",
    "unique_inline_link_clicks": "unique_inline_link_clicks",
    "unique_ctr": "unique_ctr",
    "cost_per_unique_click": "cost_per_unique_click",
    "total_actions": "total_actions",
    "total_unique_actions": "total_unique_actions",
    "result_rate": "result_rate",
    "inline_post_engagement": "inline_post_engagement",
    "cost_per_inline_post_engagement": "cost_per_inline_post_engagement",
    "auction_bid": "auction_bid",
    "auction_competitiveness": "auction_competitiveness",
    "auction_max_competitor_bid": "auction_max_competitor_bid",
    "estimated_ad_recall_rate": "estimated_ad_recall_rate",
    "estimated_ad_recallers": "estimated_ad_recallers",
}


def _is_stale(account_id: str, db) -> bool:
    from app.models.metrics import SyncJob
    ttl = timedelta(minutes=15)
    last = (
        db.query(SyncJob)
        .filter(
            SyncJob.account_id == uuid.UUID(account_id),
            SyncJob.job_type == "insights_daily",
            SyncJob.status == "completed",
        )
        .order_by(SyncJob.completed_at.desc())
        .first()
    )
    if not last or not last.completed_at:
        return True
    completed = last.completed_at
    if not completed.tzinfo:
        completed = completed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - completed) > ttl


@celery_app.task(
    name="workers.tasks.insights.sync_insights_daily_all",
    bind=True,
    max_retries=3,
)
def sync_insights_daily_all(self):
    from workers.db_helpers import get_worker_db
    from app.models.platform import Account

    with get_worker_db() as db:
        accounts = db.query(Account).filter(Account.account_status == "active", Account.platform_id == "meta").all()
        for account in accounts:
            sync_insights_for_account.delay(str(account.id))
        logger.info(f"Enqueued insights sync for {len(accounts)} accounts")


@celery_app.task(
    name="workers.tasks.insights.sync_insights_for_account",
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def sync_insights_for_account(self, account_id: str, date_preset: str = "last_7d"):
    from workers.db_helpers import (
        get_worker_db, upsert_metrics_daily, bulk_upsert_action_stats,
        create_sync_job, finalize_sync_job,
    )
    from workers.meta_client import MetaClient
    from workers.rate_limit import apply_backoff
    from app.models.platform import Account, PlatformConnection, AccountConfig
    from app.models.structure import Campaign, AdGroup, Ad
    from app.services.auth import decrypt_token

    _KEEP = {"entity_type", "entity_id", "platform_id", "account_id", "date",
             "fetched_at", "is_estimated", "attribution_window"}

    # Phase 1: reads only — extract all primitives before session closes
    with get_worker_db() as db:
        if not _is_stale(account_id, db):
            logger.info(f"[{account_id}] Insights sync skipped — fresh")
            return

        account = db.get(Account, uuid.UUID(account_id))
        if not account:
            return

        conn = db.get(PlatformConnection, account.platform_connection_id)
        if not conn or not conn.is_active:
            return

        config = db.query(AccountConfig).filter(
            AccountConfig.account_id == account.id
        ).first()
        attribution_window = config.attribution_window if config else "7d_click_1d_view"

        camp_map = {
            c.platform_campaign_id: c.id
            for c in db.query(Campaign).filter(Campaign.account_id == account.id).all()
        }
        adgroup_map = {
            ag.platform_adgroup_id: ag.id
            for ag in db.query(AdGroup).filter(AdGroup.account_id == account.id).all()
        }
        ad_map = {
            a.platform_ad_id: a.id
            for a in db.query(Ad).filter(Ad.account_id == account.id).all()
        }

        account_id_obj = account.id
        platform_id = account.platform_id
        token = decrypt_token(conn.access_token)
        ext_id = account.external_id  # already has "act_" prefix

    # Phase 2: commit "running" job before any Meta API call
    job_id = create_sync_job(account_id_obj, platform_id, "insights_daily")

    sync_breakdowns_done = False
    try:
        total_rows = 0
        client = MetaClient(token)

        def _build_scalar(entity_type, entity_id, date_str, raw):
            scalars, actions = parse_insight_row(entity_type, str(entity_id), date_str, raw)
            scalars.update({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "platform_id": platform_id,
                "account_id": account_id_obj,
                "date": date_str,
                "attribution_window": attribution_window,
            })
            for k in list(scalars.keys()):
                if k not in SCALAR_TO_DB and k not in _KEEP:
                    del scalars[k]
            for a in actions:
                a["entity_id"] = entity_id
                a["account_id"] = account_id_obj
                a["platform_id"] = platform_id
            return scalars, actions

        # ── Campaign non-unique ──────────────────────────────────────────────
        with get_worker_db() as db:
            apply_backoff(account_id)
            rows1 = client.get_insights(
                ext_id,
                fields=NON_UNIQUE_FIELDS,
                level="campaign",
                date_preset=date_preset,
                time_increment=1,
                action_attribution_windows=attribution_window,
            )
            metric_rows, action_rows = [], []
            for raw in rows1:
                entity_id = camp_map.get(raw.get("campaign_id"))
                date_str = raw.get("date_start")
                if not entity_id or not date_str:
                    continue
                s, a = _build_scalar("campaign", entity_id, date_str, raw)
                metric_rows.append(s)
                action_rows.extend(a)
            total_rows += upsert_metrics_daily(db, metric_rows)
            total_rows += bulk_upsert_action_stats(db, action_rows)

        # ── Campaign unique ──────────────────────────────────────────────────
        with get_worker_db() as db:
            apply_backoff(account_id)
            rows2 = client.get_insights(
                ext_id,
                fields=UNIQUE_FIELDS,
                level="campaign",
                date_preset=date_preset,
                time_increment=1,
            )
            unique_rows = []
            for raw in rows2:
                entity_id = camp_map.get(raw.get("campaign_id"))
                date_str = raw.get("date_start")
                if not entity_id or not date_str:
                    continue
                unique_rows.append({
                    "entity_type": "campaign", "entity_id": entity_id,
                    "platform_id": platform_id, "account_id": account_id_obj,
                    "date": date_str,
                    "reach": _coerce(raw.get("reach")),
                    "unique_clicks": _coerce(raw.get("unique_clicks")),
                    "unique_inline_link_clicks": _coerce(raw.get("unique_inline_link_clicks")),
                    "unique_ctr": _coerce(raw.get("unique_ctr")),
                })
            total_rows += upsert_metrics_daily(db, unique_rows)

        # ── Adset + Ad: per-campaign to avoid Meta 500 on large accounts ─────
        # Only iterate campaigns that had activity in this period. This bounds
        # API calls for large accounts (e.g. 1892 campaigns → only ~N active).
        # Guard: if structure sync never ran, maps will be empty and we'd silently
        # discard all rows — fail loudly so Celery retries after structure completes.
        active_campaign_ids = {
            raw.get("campaign_id")
            for raw in rows1
            if raw.get("campaign_id")
        }

        adset_nonunique, adset_unique = [], []
        ad_nonunique, ad_unique = [], []

        for platform_campaign_id in active_campaign_ids:
            apply_backoff(account_id)
            adset_nonunique.extend(client.get_insights(
                platform_campaign_id,
                fields=ADGROUP_NON_UNIQUE_FIELDS,
                level="adset",
                date_preset=date_preset,
                time_increment=1,
                action_attribution_windows=attribution_window,
            ))
            apply_backoff(account_id)
            adset_unique.extend(client.get_insights(
                platform_campaign_id,
                fields=ADGROUP_UNIQUE_FIELDS,
                level="adset",
                date_preset=date_preset,
                time_increment=1,
            ))
            apply_backoff(account_id)
            ad_nonunique.extend(client.get_insights(
                platform_campaign_id,
                fields=AD_NON_UNIQUE_FIELDS,
                level="ad",
                date_preset=date_preset,
                time_increment=1,
                action_attribution_windows=attribution_window,
            ))
            apply_backoff(account_id)
            ad_unique.extend(client.get_insights(
                platform_campaign_id,
                fields=AD_UNIQUE_FIELDS,
                level="ad",
                date_preset=date_preset,
                time_increment=1,
            ))

        if adset_nonunique and not adgroup_map:
            raise RuntimeError(
                f"[{account_id}] adgroup_map empty but Meta returned "
                f"{len(adset_nonunique)} adset rows — structure sync must complete first"
            )
        if ad_nonunique and not ad_map:
            raise RuntimeError(
                f"[{account_id}] ad_map empty but Meta returned "
                f"{len(ad_nonunique)} ad rows — structure sync must complete first"
            )

        with get_worker_db() as db:
            adgroup_metric_rows, adgroup_action_rows = [], []
            for raw in adset_nonunique:
                entity_id = adgroup_map.get(raw.get("adset_id"))
                date_str = raw.get("date_start")
                if not entity_id or not date_str:
                    continue
                s, a = _build_scalar("adgroup", entity_id, date_str, raw)
                adgroup_metric_rows.append(s)
                adgroup_action_rows.extend(a)
            total_rows += upsert_metrics_daily(db, adgroup_metric_rows)
            total_rows += bulk_upsert_action_stats(db, adgroup_action_rows)

            adgroup_unique_rows = []
            for raw in adset_unique:
                entity_id = adgroup_map.get(raw.get("adset_id"))
                date_str = raw.get("date_start")
                if not entity_id or not date_str:
                    continue
                adgroup_unique_rows.append({
                    "entity_type": "adgroup", "entity_id": entity_id,
                    "platform_id": platform_id, "account_id": account_id_obj,
                    "date": date_str,
                    "reach": _coerce(raw.get("reach")),
                    "unique_clicks": _coerce(raw.get("unique_clicks")),
                    "unique_inline_link_clicks": _coerce(raw.get("unique_inline_link_clicks")),
                    "unique_ctr": _coerce(raw.get("unique_ctr")),
                })
            total_rows += upsert_metrics_daily(db, adgroup_unique_rows)

            ad_metric_rows, ad_action_rows = [], []
            for raw in ad_nonunique:
                entity_id = ad_map.get(raw.get("ad_id"))
                date_str = raw.get("date_start")
                if not entity_id or not date_str:
                    continue
                s, a = _build_scalar("ad", entity_id, date_str, raw)
                ad_metric_rows.append(s)
                ad_action_rows.extend(a)
            total_rows += upsert_metrics_daily(db, ad_metric_rows)
            total_rows += bulk_upsert_action_stats(db, ad_action_rows)

            ad_unique_rows = []
            for raw in ad_unique:
                entity_id = ad_map.get(raw.get("ad_id"))
                date_str = raw.get("date_start")
                if not entity_id or not date_str:
                    continue
                ad_unique_rows.append({
                    "entity_type": "ad", "entity_id": entity_id,
                    "platform_id": platform_id, "account_id": account_id_obj,
                    "date": date_str,
                    "reach": _coerce(raw.get("reach")),
                    "unique_clicks": _coerce(raw.get("unique_clicks")),
                    "unique_inline_link_clicks": _coerce(raw.get("unique_inline_link_clicks")),
                    "unique_ctr": _coerce(raw.get("unique_ctr")),
                })
            total_rows += upsert_metrics_daily(db, ad_unique_rows)

        finalize_sync_job(job_id, "completed", rows_written=total_rows)
        logger.info(f"[{account_id}] Insights sync complete: {total_rows} rows")
        sync_breakdowns_done = True

    except Exception as e:
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Insights sync failed: {e}")
        raise self.retry(exc=e)

    if sync_breakdowns_done:
        sync_breakdowns_for_account.delay(account_id, date_preset)


def parse_insight_row(entity_type: str, entity_id: str, date: str, raw_row: dict):
    scalars = {}
    action_stats = []

    for field, value in raw_row.items():
        if field in SKIP_FIELDS:
            continue
        if field in ACTION_STAT_FIELDS:
            for item in (value or []):
                raw_val = item.get("value")
                action_type = item.get("action_type")
                if raw_val is None or action_type is None:
                    continue
                action_stats.append({
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "date": date,
                    "field_name": field,
                    "action_type": action_type,
                    "value": float(raw_val),
                })
        else:
            db_col = SCALAR_TO_DB.get(field)
            if db_col:
                scalars[db_col] = _coerce(value)

    return scalars, action_stats


def _coerce(value):
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        pass
    try:
        return float(value)
    except (ValueError, TypeError):
        pass
    return value


BREAKDOWN_CONFIGS = {
    "age_gender": {
        "breakdowns": "age,gender",
        "value_fn": lambda r: f"{r.get('age', '')}__{r.get('gender', '')}",
    },
    "country": {
        "breakdowns": "country",
        "value_fn": lambda r: r.get("country", ""),
    },
    "platform_position": {
        "breakdowns": "publisher_platform,platform_position",
        "value_fn": lambda r: f"{r.get('publisher_platform', '')}__{r.get('platform_position', '')}",
    },
    "device": {
        "breakdowns": "impression_device",
        "value_fn": lambda r: r.get("impression_device", ""),
    },
}

BREAKDOWN_FIELDS = "impressions,clicks,spend,ctr,cpm,cpc,date_start,date_stop"


@celery_app.task(
    name="workers.tasks.insights.sync_breakdowns_for_account",
    bind=True,
    max_retries=3,
    retry_backoff=True,
)
def sync_breakdowns_for_account(self, account_id: str, date_preset: str = "last_7d"):
    from workers.db_helpers import get_worker_db
    from workers.meta_client import MetaClient, MetaAPIError
    from workers.rate_limit import apply_backoff
    from app.models.platform import Account, PlatformConnection
    from app.models.metrics import MetricBreakdowns
    from app.services.auth import decrypt_token
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    with get_worker_db() as db:
        account = db.get(Account, uuid.UUID(account_id))
        if not account:
            return
        conn = db.get(PlatformConnection, account.platform_connection_id)
        if not conn or not conn.is_active:
            return

        token = decrypt_token(conn.access_token)
        ext_id = account.external_id.replace("act_", "")

        try:
            client = MetaClient(token)
            total = 0

            for bd_type, cfg in BREAKDOWN_CONFIGS.items():
                apply_backoff(account_id)
                params = {
                    "fields": BREAKDOWN_FIELDS,
                    "level": "account",
                    "date_preset": date_preset,
                    "time_increment": 1,
                    "breakdowns": cfg["breakdowns"],
                    "limit": 500,
                }
                rows, _ = client.get(f"/act_{ext_id}/insights", params)
                data = rows.get("data", [])

                bd_rows = []
                for r in data:
                    date_str = r.get("date_start")
                    if not date_str:
                        continue
                    val = cfg["value_fn"](r)
                    if not val:
                        continue
                    bd_rows.append({
                        "entity_type": "account",
                        "entity_id": account.id,
                        "platform_id": account.platform_id,
                        "account_id": account.id,
                        "date": date_str,
                        "breakdown_type": bd_type,
                        "breakdown_value": val,
                        "impressions": _coerce(r.get("impressions")),
                        "clicks": _coerce(r.get("clicks")),
                        "spend": _coerce(r.get("spend")),
                        "ctr": _coerce(r.get("ctr")),
                        "cpm": _coerce(r.get("cpm")),
                        "cpc": _coerce(r.get("cpc")),
                        "fetched_at": datetime.now(timezone.utc),
                    })

                if bd_rows:
                    stmt = pg_insert(MetricBreakdowns).values(bd_rows)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["entity_id", "date", "breakdown_type", "breakdown_value"],
                        set_={
                            "impressions": stmt.excluded.impressions,
                            "clicks": stmt.excluded.clicks,
                            "spend": stmt.excluded.spend,
                            "ctr": stmt.excluded.ctr,
                            "cpm": stmt.excluded.cpm,
                            "cpc": stmt.excluded.cpc,
                            "fetched_at": stmt.excluded.fetched_at,
                        },
                    )
                    db.execute(stmt)
                    total += len(bd_rows)
                    logger.info(f"[{account_id}] Breakdown {bd_type}: {len(bd_rows)} rows")

            logger.info(f"[{account_id}] Breakdown sync complete: {total} rows")

        except MetaAPIError as e:
            logger.error(f"[{account_id}] Breakdown sync failed: {e}")
            raise self.retry(exc=e)
