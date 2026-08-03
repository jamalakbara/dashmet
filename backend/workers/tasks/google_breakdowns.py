"""
Google Ads breakdown sync worker.
Fetches account-level demographic/device/geo breakdowns via GAQL and writes one
whole-period aggregate per segment into metric_breakdowns (same model + delete-
then-insert pattern as the TikTok breakdown worker). breakdown_type values match
Meta/TikTok so the frontend renders without changes.
Schedule: every 1 hour via Celery Beat.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from workers.celery_app import celery_app, HEAVY_SOFT_TIME_LIMIT, HEAVY_TIME_LIMIT, LOCK_TTL

logger = logging.getLogger(__name__)

STALE_THRESHOLD = timedelta(hours=1)

_METRICS = "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions"

# Google AgeRangeType / GenderType enum → Meta-style values the frontend expects.
_AGE_MAP = {
    "AGE_RANGE_18_24": "18-24", "AGE_RANGE_25_34": "25-34", "AGE_RANGE_35_44": "35-44",
    "AGE_RANGE_45_54": "45-54", "AGE_RANGE_55_64": "55-64", "AGE_RANGE_65_UP": "65+",
    "AGE_RANGE_UNDETERMINED": "unknown",
}
_GENDER_MAP = {"MALE": "male", "FEMALE": "female", "UNDETERMINED": "unknown"}


def _f(raw: dict, key: str) -> float:
    v = raw.get(key)
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _aggregate(rows: list[dict], value_fn) -> dict:
    """Sum core metrics across all returned rows, grouped by breakdown value."""
    agg: dict[str, dict] = {}
    for raw in rows:
        val = value_fn(raw)
        if not val:
            continue
        a = agg.setdefault(val, {"impressions": 0.0, "clicks": 0.0, "spend": 0.0, "conversions": 0.0})
        a["impressions"] += _f(raw, "metrics.impressions")
        a["clicks"] += _f(raw, "metrics.clicks")
        a["spend"] += _f(raw, "metrics.cost_micros") / 1_000_000
        a["conversions"] += _f(raw, "metrics.conversions")
    return agg


def _bd_rows(account_uuid, start_date, breakdown_type, agg) -> list[dict]:
    now = datetime.now(timezone.utc)
    out = []
    for value, m in agg.items():
        impr, clicks, spend = m["impressions"], m["clicks"], m["spend"]
        out.append({
            "entity_type": "account",
            "entity_id": account_uuid,
            "platform_id": "google_ads",
            "account_id": account_uuid,
            "date": start_date,
            "breakdown_type": breakdown_type,
            "breakdown_value": value,
            "impressions": int(impr) or None,
            "clicks": int(clicks) or None,
            "spend": spend or None,
            "conversions": m["conversions"] or None,
            "ctr": (clicks / impr * 100) if impr else None,
            "cpm": (spend / impr * 1000) if impr else None,
            "cpc": (spend / clicks) if clicks else None,
            "fetched_at": now,
        })
    return out


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
    name="workers.tasks.google_breakdowns.sync_google_breakdowns_all",
    bind=True,
    max_retries=3,
)
def sync_google_breakdowns_all(self):
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
    count = stagger_dispatch(sync_google_breakdowns_for_account, pairs)
    logger.info("Enqueued Google breakdown sync for %s accounts", count)


@celery_app.task(
    name="workers.tasks.google_breakdowns.sync_google_breakdowns_for_account",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def sync_google_breakdowns_for_account(self, account_id: str, date_preset: str = "last_30d"):
    from celery.exceptions import SoftTimeLimitExceeded
    from workers.db_helpers import get_worker_db, create_sync_job, finalize_sync_job
    from workers.rate_limit import acquire_lock, release_lock, pause_connection
    from app.models.platform import Account, PlatformConnection
    from app.models.metrics import MetricBreakdowns
    from app.services.auth import decrypt_token
    from app.services.insights import resolve_date_range
    from workers.google_client import GoogleClient, GoogleAdsClientError

    account_uuid = uuid.UUID(account_id)

    lock_token = acquire_lock("google_breakdowns", account_id, LOCK_TTL)
    if not lock_token:
        logger.info("Google breakdowns already running for %s — skip", account_id)
        return

    job_id = create_sync_job(account_uuid, "google_ads", "breakdown")
    connection_id = None

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
            connection_id = str(conn.id)
            refresh_token = decrypt_token(conn.refresh_token)
            customer_id = account.external_id
            account_timezone = account.timezone

        start, end = resolve_date_range(date_preset, account_timezone)
        start_str, end_str = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        date_clause = f"WHERE segments.date BETWEEN '{start_str}' AND '{end_str}'"

        # breakdown_type → accumulated rows (age + gender share "age_gender").
        results: dict[str, list[dict]] = {}

        with GoogleClient(refresh_token) as client:
            # Device
            rows = client.search(customer_id, f"SELECT segments.device, {_METRICS} FROM campaign {date_clause}")
            agg = _aggregate(rows, lambda r: r.get("segments.device"))
            results.setdefault("device", []).extend(_bd_rows(account_uuid, start, "device", agg))

            # Age (age_range_view) — stored as "{age}__"
            rows = client.search(
                customer_id,
                f"SELECT ad_group_criterion.age_range.type, {_METRICS} FROM age_range_view {date_clause}",
            )
            agg = _aggregate(rows, lambda r: _AGE_MAP.get(r.get("ad_group_criterion.age_range.type", ""), ""))
            results.setdefault("age_gender", []).extend(
                _bd_rows(account_uuid, start, "age_gender", {f"{k}__": v for k, v in agg.items()})
            )

            # Gender (gender_view) — stored as "__{gender}"
            rows = client.search(
                customer_id,
                f"SELECT ad_group_criterion.gender.type, {_METRICS} FROM gender_view {date_clause}",
            )
            agg = _aggregate(rows, lambda r: _GENDER_MAP.get(r.get("ad_group_criterion.gender.type", ""), ""))
            results.setdefault("age_gender", []).extend(
                _bd_rows(account_uuid, start, "age_gender", {f"__{k}": v for k, v in agg.items()})
            )

            # Country (geographic_view → country_criterion_id → ISO code via geo_target_constant)
            rows = client.search(
                customer_id,
                f"SELECT geographic_view.country_criterion_id, {_METRICS} FROM geographic_view {date_clause}",
            )
            geo_ids = {str(r.get("geographic_view.country_criterion_id", "")) for r in rows if r.get("geographic_view.country_criterion_id")}
            code_map: dict[str, str] = {}
            if geo_ids:
                id_list = ", ".join(f"'{gid}'" for gid in geo_ids)
                geo_rows = client.search(
                    customer_id,
                    f"SELECT geo_target_constant.id, geo_target_constant.country_code "
                    f"FROM geo_target_constant WHERE geo_target_constant.id IN ({id_list})",
                )
                code_map = {
                    str(g.get("geo_target_constant.id")): g.get("geo_target_constant.country_code", "")
                    for g in geo_rows
                }
            agg = _aggregate(rows, lambda r: code_map.get(str(r.get("geographic_view.country_criterion_id", "")), ""))
            results.setdefault("country", []).extend(_bd_rows(account_uuid, start, "country", agg))

        total = 0
        for bd_type, bd_rows in results.items():
            if not bd_rows:
                continue
            with get_worker_db() as db:
                # One whole-period aggregate keyed by start_date (which shifts daily) —
                # purge the prior set for this account+type before inserting the fresh
                # one so the API's date-range SUM never double-counts.
                db.execute(
                    MetricBreakdowns.__table__.delete().where(
                        MetricBreakdowns.entity_id == account_uuid,
                        MetricBreakdowns.platform_id == "google_ads",
                        MetricBreakdowns.breakdown_type == bd_type,
                    )
                )
                stmt = pg_insert(MetricBreakdowns).values(bd_rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["entity_id", "date", "breakdown_type", "breakdown_value"],
                    set_={
                        "impressions": stmt.excluded.impressions,
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
            logger.info("[%s] Google breakdown %s: %s rows", account_id, bd_type, len(bd_rows))

        finalize_sync_job(job_id, "completed", rows_written=total)
        logger.info("[%s] Google breakdown sync complete: %s rows", account_id, total)

    except SoftTimeLimitExceeded as exc:
        logger.error("Google breakdown sync for %s exceeded soft time limit", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        return
    except GoogleAdsClientError as exc:
        if exc.is_quota:
            if connection_id:
                pause_connection(connection_id, 300)
            logger.warning("Google quota hit for %s — rescheduling breakdowns in 300s", account_id)
            finalize_sync_job(job_id, "skipped")
            self.apply_async(args=[account_id, date_preset], countdown=300)
            return
        logger.error("Google API error for breakdowns %s: %s", account_id, exc)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error in Google breakdown sync for %s", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    finally:
        release_lock("google_breakdowns", account_id, lock_token)
