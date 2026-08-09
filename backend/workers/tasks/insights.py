"""
Sync worker — Insights (daily metrics)
Fetches scalar + action metrics from Meta Insights API and upserts into DB.
Schedule: every 15 minutes via Celery Beat.
"""
import json
import logging
import re
import urllib.parse as _up
import uuid
from datetime import datetime, timedelta, timezone

from workers.celery_app import celery_app, HEAVY_SOFT_TIME_LIMIT, HEAVY_TIME_LIMIT, LOCK_TTL

# Max sub-requests per Meta batch call (platform hard limit is 50).
_BATCH_SIZE = 50

logger = logging.getLogger(__name__)

_METRIC_FIELDS = ",".join([
    "impressions", "clicks", "spend", "ctr", "cpm", "cpc", "cpp",
    "frequency", "inline_link_clicks", "inline_link_click_ctr",
    "cost_per_inline_link_click",
    "inline_post_engagement", "cost_per_inline_post_engagement",
    "estimated_ad_recall_rate", "estimated_ad_recallers",
    "outbound_clicks", "outbound_clicks_ctr", "cost_per_outbound_click",
    "actions", "action_values", "cost_per_action_type",
    "purchase_roas", "website_purchase_roas",
    "video_play_actions", "video_avg_time_watched_actions",
    "video_continuous_2_sec_watched_actions",
    "video_p25_watched_actions", "video_p50_watched_actions",
    "video_p75_watched_actions", "video_p100_watched_actions",
    "video_thruplay_watched_actions",
    # CPAS (Collaborative Ads / "shared item"): for catalog-segment accounts the
    # retailer owns the pixel, so regular actions/action_values/purchase_roas come
    # back empty — catalog_segment_* is the ONLY source of CPAS conversions. These
    # fields are universally valid and return empty (not an error) for non-catalog
    # accounts, so requesting them unconditionally for all Meta accounts is safe.
    "catalog_segment_actions", "catalog_segment_value",
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
    # CPAS shared-item conversions — see _METRIC_FIELDS comment. Persisted into
    # metric_action_stats as (field_name, action_type, value) with normalized types.
    "catalog_segment_actions", "catalog_segment_value",
}

# CPAS shared-item provenance: with Collaborative Ads the retailer owns the pixel,
# and Meta returns catalog_segment_* action types in varying forms depending on the
# retailer's pixel setup — offsite_conversion.fb_pixel_*, omni_*, or bare names.
# Normalize to clean canonical action types so the read layer has a stable contract
# to pivot on. Substring-matched (order matters: check specific buckets by keyword).
# Scoped to catalog_segment_* fields ONLY — regular actions/action_values are stored
# verbatim. Unknown catalog_segment types are stored as-is (not dropped) — a
# restated/unknown type is still data.
_CATALOG_SEGMENT_ACTION_BUCKETS = (
    ("purchase", "purchase"),
    ("add_to_cart", "add_to_cart"),
    ("view_content", "view_content"),
)


def _normalize_catalog_segment_action(action_type: str) -> str:
    for keyword, canonical in _CATALOG_SEGMENT_ACTION_BUCKETS:
        if keyword in action_type:
            return canonical
    return action_type

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
    from workers.dispatch import stagger_dispatch
    from app.models.platform import Account

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(Account.account_status == "active", Account.platform_id == "meta")
            .all()
        ]
    count = stagger_dispatch(sync_insights_for_account, pairs)
    logger.info(f"Enqueued insights sync for {count} accounts")


@celery_app.task(
    name="workers.tasks.insights.sync_breakdowns_all",
    bind=True,
    max_retries=3,
)
def sync_breakdowns_all(self):
    from workers.db_helpers import get_worker_db
    from workers.dispatch import stagger_dispatch
    from app.models.platform import Account

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(Account.account_status == "active", Account.platform_id == "meta")
            .all()
        ]
    count = stagger_dispatch(sync_breakdowns_for_account, pairs, extra_args=("last_30d",))
    logger.info(f"Enqueued breakdown sync for {count} accounts")


@celery_app.task(
    name="workers.tasks.insights.sync_insights_for_account",
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def sync_insights_for_account(self, account_id: str, date_preset: str = "last_7d", force: bool = False):
    from celery.exceptions import SoftTimeLimitExceeded
    from workers.db_helpers import (
        get_worker_db, upsert_metrics_daily, bulk_upsert_action_stats,
        create_sync_job, finalize_sync_job,
    )
    from workers.meta_client import MetaClient, MetaAPIError
    from workers.rate_limit import (
        apply_backoff, RateLimitBackoff,
        acquire_lock, release_lock, connection_paused_remaining,
        pause_connection, is_meta_rate_limit_error, HARD_PAUSE_SECONDS,
    )
    from app.models.platform import Account, PlatformConnection, AccountConfig
    from app.models.structure import Campaign, AdGroup, Ad
    from app.services.auth import decrypt_token

    _KEEP = {"entity_type", "entity_id", "platform_id", "account_id", "date",
             "fetched_at", "is_estimated", "attribution_window"}

    # Phase 1: reads only — extract all primitives before session closes
    with get_worker_db() as db:
        if not force and not _is_stale(account_id, db):
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
        connection_id = str(conn.id)
        token = decrypt_token(conn.access_token)
        ext_id = account.external_id  # already has "act_" prefix
        # Resolve preset → explicit time_range in the account tz once, up front —
        # the same resolver the read path uses, so synced days == queried days (§2.3).
        from workers.date_range import meta_time_range
        time_range = meta_time_range(date_preset, account.timezone)

    # Gate: skip the whole token while it's rate-limit paused (shared app quota)
    paused = connection_paused_remaining(connection_id)
    if paused > 0:
        logger.info(f"[{account_id}] Connection paused {paused}s — rescheduling")
        self.apply_async(args=[account_id, date_preset, force], countdown=paused)
        return

    # Overlap guard: only one insights run per account at a time
    lock_token = acquire_lock("insights_daily", account_id, LOCK_TTL)
    if not lock_token:
        logger.info(f"[{account_id}] Insights sync already running — skip")
        return

    # Phase 2: commit "running" job before any Meta API call
    job_id = create_sync_job(account_id_obj, platform_id, "insights_daily")

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
            apply_backoff(account_id, connection_id)
            rows1 = client.get_insights(
                ext_id,
                fields=NON_UNIQUE_FIELDS,
                level="campaign",
                time_range=time_range,
                time_increment=1,
                action_attribution_windows=attribution_window,
                account_id=account_id,
                connection_id=connection_id,
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
            apply_backoff(account_id, connection_id)
            rows2 = client.get_insights(
                ext_id,
                fields=UNIQUE_FIELDS,
                level="campaign",
                time_range=time_range,
                time_increment=1,
                account_id=account_id,
                connection_id=connection_id,
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

        # Build all 4 sub-requests per campaign upfront, then fire in batches of
        # _BATCH_SIZE (50). Each batch = 1 HTTP round-trip instead of 4×N sequential
        # calls. apply_backoff once per chunk (not per call) — still checks Redis state
        # before each batch, but cuts round-trips by 75%.
        # Caveat: batch doesn't auto-paginate. limit=500 covers all but unusually large
        # campaigns (>500 adsets or >500 ads); those get truncated to 500 rows.
        aw_json = json.dumps(
            re.findall(r"\d+d_(?:click|view|engaged_view)", attribution_window)
            or [attribution_window]
        ) if attribution_window else None

        _specs = [
            (ADGROUP_NON_UNIQUE_FIELDS, "adset", "adset_nonunique", aw_json),
            (ADGROUP_UNIQUE_FIELDS,     "adset", "adset_unique",    None),
            (AD_NON_UNIQUE_FIELDS,      "ad",    "ad_nonunique",    aw_json),
            (AD_UNIQUE_FIELDS,          "ad",    "ad_unique",       None),
        ]
        batch_requests: list[dict] = []
        batch_tags: list[tuple[str, str]] = []
        for pid in active_campaign_ids:
            for fields, level, tag, aw in _specs:
                batch_requests.append({
                    "method": "GET",
                    "relative_url": _campaign_batch_url(pid, fields, level, time_range, 1, aw),
                })
                batch_tags.append((pid, tag))

        for _i in range(0, len(batch_requests), _BATCH_SIZE):
            apply_backoff(account_id, connection_id)
            chunk = batch_requests[_i:_i + _BATCH_SIZE]
            tags = batch_tags[_i:_i + _BATCH_SIZE]
            results = client.batch(chunk, account_id=account_id, connection_id=connection_id)
            for (pid, kind), result in zip(tags, results):
                if "error" in result:
                    err = result["error"]
                    code = err.get("code", 0)
                    subcode = err.get("error_subcode")
                    if is_meta_rate_limit_error(code, subcode):
                        pause_connection(connection_id, HARD_PAUSE_SECONDS)
                        raise RateLimitBackoff(HARD_PAUSE_SECONDS, scope="connection")
                    logger.warning(
                        "[%s] Batch sub-request error campaign=%s kind=%s code=%s: %s",
                        account_id, pid, kind, code, err.get("message"),
                    )
                    continue
                data = result.get("data", [])
                if kind == "adset_nonunique":
                    adset_nonunique.extend(data)
                elif kind == "adset_unique":
                    adset_unique.extend(data)
                elif kind == "ad_nonunique":
                    ad_nonunique.extend(data)
                elif kind == "ad_unique":
                    ad_unique.extend(data)

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

    except RateLimitBackoff as b:
        # Rate limited mid-run: reschedule the whole task (idempotent upserts).
        # Off the error-retry budget so a throttled account isn't marked failed.
        finalize_sync_job(job_id, "skipped")
        logger.info(f"[{account_id}] Insights rescheduled in {b.countdown}s ({b.scope})")
        self.apply_async(args=[account_id, date_preset, force], countdown=b.countdown)
        return
    except SoftTimeLimitExceeded as e:
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Insights sync exceeded soft time limit")
        return
    except MetaAPIError as e:
        if is_meta_rate_limit_error(e.code, e.subcode):
            pause_connection(connection_id, HARD_PAUSE_SECONDS)
            finalize_sync_job(job_id, "skipped")
            logger.warning(f"[{account_id}] Meta rate-limit error (code {e.code}) — pausing connection {HARD_PAUSE_SECONDS}s")
            self.apply_async(args=[account_id, date_preset, force], countdown=HARD_PAUSE_SECONDS)
            return
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Insights sync failed: {e}")
        raise self.retry(exc=e)
    except Exception as e:
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Insights sync failed: {e}")
        raise self.retry(exc=e)
    finally:
        release_lock("insights_daily", account_id, lock_token)


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
                # CPAS shared-item fields: normalize varying pixel-dependent
                # action types to canonical purchase/add_to_cart/view_content.
                if field in ("catalog_segment_actions", "catalog_segment_value"):
                    action_type = _normalize_catalog_segment_action(action_type)
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


def _campaign_batch_url(campaign_id: str, fields: str, level: str, time_range: str,
                        time_increment: int = 1, aw_json: str | None = None) -> str:
    """Relative URL for a Meta batch sub-request (per-campaign insights)."""
    params: list[tuple[str, str]] = [
        ("fields", fields),
        ("level", level),
        ("time_range", time_range),
        ("time_increment", str(time_increment)),
        ("limit", "500"),
    ]
    if aw_json:
        params.append(("action_attribution_windows", aw_json))
    return f"/{campaign_id}/insights?" + _up.urlencode(params)


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

BREAKDOWN_FIELDS = "impressions,reach,clicks,spend,ctr,cpm,cpc,actions,date_start,date_stop"


@celery_app.task(
    name="workers.tasks.insights.sync_breakdowns_for_account",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def sync_breakdowns_for_account(self, account_id: str, date_preset: str = "last_30d"):
    from celery.exceptions import SoftTimeLimitExceeded
    from workers.db_helpers import get_worker_db, create_sync_job, finalize_sync_job
    from workers.meta_client import MetaClient, MetaAPIError
    from workers.rate_limit import (
        apply_backoff, RateLimitState, RateLimitBackoff,
        acquire_lock, release_lock, connection_paused_remaining,
        pause_connection, is_meta_rate_limit_error, HARD_PAUSE_SECONDS,
    )
    from app.models.platform import Account, PlatformConnection, AccountConfig
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
        connection_id = str(conn.id)
        account_id_obj = account.id
        platform_id = account.platform_id
        account_tz = account.timezone
        config = (
            db.query(AccountConfig)
            .filter(AccountConfig.account_id == account.id)
            .first()
        )
        primary_conversion_action = (
            config.primary_conversion_action
            if config and config.primary_conversion_action
            else "purchase"
        )

    paused = connection_paused_remaining(connection_id)
    if paused > 0:
        logger.info(f"[{account_id}] Connection paused {paused}s — rescheduling breakdowns")
        self.apply_async(args=[account_id, date_preset], countdown=paused)
        return

    lock_token = acquire_lock("breakdowns", account_id, LOCK_TTL)
    if not lock_token:
        logger.info(f"[{account_id}] Breakdown sync already running — skip")
        return

    # Commit a "running" job before the first API call (P-8) so the breakdown
    # section/badge can tell "syncing" from "done" — without this, job_type
    # "breakdown" has no producer and the badge is stuck "partially synced".
    job_id = create_sync_job(account_id_obj, platform_id, "breakdown")

    try:
        # Resolve preset → explicit time_range in the account tz (§2.3): same
        # resolver as the read path, so breakdown days == queried days.
        from workers.date_range import meta_time_range
        time_range = meta_time_range(date_preset, account_tz)
        with get_worker_db() as db:
            client = MetaClient(token)
            total = 0

            for bd_type, cfg in BREAKDOWN_CONFIGS.items():
                apply_backoff(account_id, connection_id)
                params = {
                    "fields": BREAKDOWN_FIELDS,
                    "level": "account",
                    "time_range": time_range,
                    "time_increment": 1,
                    "breakdowns": cfg["breakdowns"],
                    "limit": 500,
                }
                rows, rate_limits = client.get(f"/act_{ext_id}/insights", params)
                RateLimitState(account_id, connection_id).update_from_headers(rate_limits)
                data = rows.get("data", [])

                bd_rows = []
                for r in data:
                    date_str = r.get("date_start")
                    if not date_str:
                        continue
                    val = cfg["value_fn"](r)
                    if not val:
                        continue
                    # Conversions come back inside the `actions` array — pull the
                    # account's primary conversion action out for the breakdown column.
                    conv_val = None
                    for a in (r.get("actions") or []):
                        if a.get("action_type") == primary_conversion_action:
                            try:
                                conv_val = float(a.get("value"))
                            except (TypeError, ValueError):
                                conv_val = None
                            break
                    bd_rows.append({
                        "entity_type": "account",
                        "entity_id": account_id_obj,
                        "platform_id": platform_id,
                        "account_id": account_id_obj,
                        "date": date_str,
                        "breakdown_type": bd_type,
                        "breakdown_value": val,
                        "impressions": _coerce(r.get("impressions")),
                        "reach": _coerce(r.get("reach")),
                        "clicks": _coerce(r.get("clicks")),
                        "spend": _coerce(r.get("spend")),
                        "conversions": conv_val,
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
                    logger.info(f"[{account_id}] Breakdown {bd_type}: {len(bd_rows)} rows")

            logger.info(f"[{account_id}] Breakdown sync complete: {total} rows")

        finalize_sync_job(job_id, "completed", rows_written=total)

    except RateLimitBackoff as b:
        # Throttled mid-run: reschedule off the error-retry budget (skipped, not failed).
        finalize_sync_job(job_id, "skipped")
        logger.info(f"[{account_id}] Breakdown rescheduled in {b.countdown}s ({b.scope})")
        self.apply_async(args=[account_id, date_preset], countdown=b.countdown)
        return
    except SoftTimeLimitExceeded as e:
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Breakdown sync exceeded soft time limit")
        return
    except MetaAPIError as e:
        if is_meta_rate_limit_error(e.code, e.subcode):
            pause_connection(connection_id, HARD_PAUSE_SECONDS)
            finalize_sync_job(job_id, "skipped")
            logger.warning(f"[{account_id}] Breakdown Meta rate-limit (code {e.code}) — pausing connection {HARD_PAUSE_SECONDS}s")
            self.apply_async(args=[account_id, date_preset], countdown=HARD_PAUSE_SECONDS)
            return
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Breakdown sync failed: {e}")
        raise self.retry(exc=e)
    except Exception as e:
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Breakdown sync failed: {e}")
        raise self.retry(exc=e)
    finally:
        release_lock("breakdowns", account_id, lock_token)
