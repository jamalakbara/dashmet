"""
Sync worker — Structure
Fetches campaigns, ad groups, and ads from Meta API and upserts into DB.
Schedule: every 30 minutes via Celery Beat.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from workers.celery_app import celery_app, HEAVY_SOFT_TIME_LIMIT, HEAVY_TIME_LIMIT, LOCK_TTL

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "ACTIVE": "active",
    "PAUSED": "paused",
    "DELETED": "deleted",
    "ARCHIVED": "archived",
}
OBJECTIVE_MAP = {
    "OUTCOME_AWARENESS": "awareness",
    "OUTCOME_TRAFFIC": "traffic",
    "OUTCOME_ENGAGEMENT": "engagement",
    "OUTCOME_LEADS": "leads",
    "OUTCOME_APP_PROMOTION": "app_promotion",
    "OUTCOME_SALES": "sales",
}
CAMPAIGN_FIELDS = (
    "id,name,status,effective_status,objective,"
    "daily_budget,lifetime_budget,buying_type,"
    "start_time,stop_time,created_time,updated_time"
)
ADSET_FIELDS = (
    "id,name,status,effective_status,campaign_id,"
    "optimization_goal,billing_event,bid_amount,"
    "daily_budget,lifetime_budget,targeting,"
    "start_time,stop_time,created_time,updated_time"
)
AD_FIELDS = (
    "id,name,status,effective_status,"
    "adset_id,campaign_id,creative{id},"
    "created_time,updated_time"
)


def _cents_to_units(value_str) -> float | None:
    if value_str is None:
        return None
    try:
        return int(value_str) / 100
    except (ValueError, TypeError):
        return None


def _parse_date(dt_str) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("+0000", "+00:00"))
    except Exception:
        return None


def _is_stale(account_id: str, db) -> bool:
    from app.models.metrics import SyncJob
    ttl = timedelta(minutes=30)
    last = (
        db.query(SyncJob)
        .filter(
            SyncJob.account_id == uuid.UUID(account_id),
            SyncJob.job_type == "structure",
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


META_ACCOUNT_STATUS_MAP = {
    1: "active",
    2: "disabled",     # DISABLED
    3: "unsettled",    # UNSETTLED (unpaid balance — data still readable)
    7: "unsettled",    # PENDING_RISK_REVIEW
    8: "unsettled",    # PENDING_SETTLEMENT
    9: "active",       # IN_GRACE_PERIOD
    100: "disabled",   # PENDING_CLOSURE
    101: "disabled",   # CLOSED
}


@celery_app.task(
    name="workers.tasks.structure.sync_accounts_for_connection",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_accounts_for_connection(self, connection_id: str, org_id: str):
    from workers.db_helpers import get_worker_db
    from workers.meta_client import MetaClient, MetaAPIError
    from app.models.platform import Account, PlatformConnection
    from app.services.auth import decrypt_token

    with get_worker_db() as db:
        conn = db.get(PlatformConnection, uuid.UUID(connection_id))
        if not conn or not conn.is_active:
            logger.warning(f"[conn:{connection_id}] No active connection")
            return

        conn_uuid = conn.id  # keep a primitive for use after the session closes
        token = decrypt_token(conn.access_token)

        try:
            client = MetaClient(token)
            try:
                ad_accounts = client.paginate(
                    "/me/adaccounts",
                    {"fields": "id,name,currency,timezone_name,account_status,business"},
                )
            except MetaAPIError as e:
                if e.code == 100:
                    # Token lacks business_management permission — retry without business field
                    logger.warning(f"[conn:{connection_id}] No business_management permission, fetching without business field")
                    ad_accounts = client.paginate(
                        "/me/adaccounts",
                        {"fields": "id,name,currency,timezone_name,account_status"},
                    )
                else:
                    raise
        except MetaAPIError as e:
            if e.is_auth:
                from workers.token_alerts import alert_connection_token_failure
                alert_connection_token_failure(
                    connection_id, platform_label="Meta", detail=str(e)
                )
            logger.error(f"[conn:{connection_id}] Failed to fetch ad accounts: {e}")
            raise self.retry(exc=e)

        now = datetime.now(timezone.utc)
        org_uuid = uuid.UUID(org_id)

        for acc in ad_accounts:
            raw_id = acc.get("id", "")
            external_id = raw_id if raw_id.startswith("act_") else f"act_{raw_id}"
            status_int = acc.get("account_status", 1)
            # Unknown/unrecognized status defaults to "unsettled", never "disabled":
            # a status we don't recognize must stay visible and syncable rather than
            # silently vanishing the account (P-2/P-4). Only known terminal states
            # (DISABLED/PENDING_CLOSURE/CLOSED) map to "disabled".
            status = META_ACCOUNT_STATUS_MAP.get(status_int, "unsettled")
            business = acc.get("business") or {}

            stmt = pg_insert(Account).values(
                organization_id=org_uuid,
                platform_connection_id=conn.id,
                platform_id=conn.platform_id,
                external_id=external_id,
                name=acc.get("name", external_id),
                currency=acc.get("currency", "USD"),
                timezone=acc.get("timezone_name", "UTC"),
                account_status=status,
                business_id=str(business.get("id")) if business.get("id") else None,
                business_name=business.get("name"),
                synced_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["organization_id", "platform_id", "external_id"],
                set_={
                    "name": stmt.excluded.name,
                    "currency": stmt.excluded.currency,
                    "timezone": stmt.excluded.timezone,
                    "account_status": stmt.excluded.account_status,
                    "business_id": stmt.excluded.business_id,
                    "business_name": stmt.excluded.business_name,
                    "platform_connection_id": stmt.excluded.platform_connection_id,
                    "synced_at": stmt.excluded.synced_at,
                },
            )
            db.execute(stmt)

        db.flush()

        # Ensure every imported account has a config row with sensible defaults
        from app.models.platform import AccountConfig
        imported = (
            db.query(Account)
            .filter(
                Account.organization_id == org_uuid,
                Account.platform_id == conn.platform_id,
            )
            .all()
        )
        existing_config_ids = {
            r.account_id
            for r in db.query(AccountConfig.account_id)
            .filter(AccountConfig.account_id.in_([a.id for a in imported]))
            .all()
        }
        for account in imported:
            if account.id not in existing_config_ids:
                db.add(AccountConfig(account_id=account.id))

        db.commit()
        logger.info(f"[conn:{connection_id}] Imported {len(ad_accounts)} ad accounts")

    # Recovery (P-2): a clean account import clears any prior token alert for this
    # connection. Helper self-guards on last_error and swallows its own errors.
    from workers.token_alerts import clear_connection_token_failure
    clear_connection_token_failure(connection_id)

    # Structure fans out globally (staggered, skips-fresh — cheap).
    sync_structure_all.delay()

    # D-lite (F/§P-5): don't make a freshly-connected user wait for the next
    # 15-min/hourly beat for their KPIs and breakdowns. Eager-enqueue insights +
    # breakdown, but scoped to *this connection's* accounts and via
    # stagger_dispatch (not raw .delay) so we don't burst the shared token.
    # Scoping matters for breakdown especially: it has no staleness guard, so a
    # global fan-out would re-fetch every account's breakdowns on every connect.
    # insights runs its retry-until-structure-ready guard if it lands first.
    from workers.tasks.insights import sync_insights_for_account, sync_breakdowns_for_account
    from workers.dispatch import stagger_dispatch

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(
                Account.platform_connection_id == conn_uuid,
                Account.account_status != "disabled",
            )
            .all()
        ]
    n_ins = stagger_dispatch(sync_insights_for_account, pairs)
    n_bd = stagger_dispatch(sync_breakdowns_for_account, pairs, extra_args=("last_30d",))
    logger.info(f"[conn:{connection_id}] Eager first sync — insights:{n_ins} breakdowns:{n_bd}")


@celery_app.task(
    name="workers.tasks.structure.sync_structure_all",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_structure_all(self):
    from workers.db_helpers import get_worker_db
    from workers.dispatch import stagger_dispatch
    from app.models.platform import Account

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(Account.account_status != "disabled", Account.platform_id == "meta")
            .all()
        ]
    count = stagger_dispatch(sync_structure_for_account, pairs)
    logger.info(f"Enqueued structure sync for {count} accounts")


@celery_app.task(
    name="workers.tasks.structure.sync_structure_for_account",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def sync_structure_for_account(self, account_id: str):
    from celery.exceptions import SoftTimeLimitExceeded
    from workers.db_helpers import get_worker_db, create_sync_job, finalize_sync_job
    from workers.meta_client import MetaClient, MetaAPIError
    from workers.rate_limit import (
        apply_backoff, RateLimitBackoff,
        acquire_lock, release_lock, connection_paused_remaining,
        pause_connection, is_meta_rate_limit_error, HARD_PAUSE_SECONDS,
    )
    from app.models.platform import Account, PlatformConnection
    from app.models.structure import Campaign, AdGroup, Ad
    from app.services.auth import decrypt_token

    # Phase 1: reads only — extract all primitives before session closes
    with get_worker_db() as db:
        if not _is_stale(account_id, db):
            logger.info(f"[{account_id}] Structure sync skipped — fresh")
            return

        account = db.get(Account, uuid.UUID(account_id))
        if not account:
            logger.error(f"[{account_id}] Account not found")
            return

        conn = db.get(PlatformConnection, account.platform_connection_id)
        if not conn or not conn.is_active:
            logger.warning(f"[{account_id}] No active connection")
            return

        account_id_obj = account.id
        platform_id = account.platform_id
        connection_id = str(conn.id)
        token = decrypt_token(conn.access_token)
        ext_id = account.external_id.replace("act_", "")

    # Gate: skip the whole token while it's rate-limit paused (shared app quota)
    paused = connection_paused_remaining(connection_id)
    if paused > 0:
        logger.info(f"[{account_id}] Connection paused {paused}s — rescheduling structure")
        self.apply_async(args=[account_id], countdown=paused)
        return

    # Overlap guard: only one structure run per account at a time
    lock_token = acquire_lock("structure", account_id, LOCK_TTL)
    if not lock_token:
        logger.info(f"[{account_id}] Structure sync already running — skip")
        return

    # Phase 2: commit "running" job before any Meta API call
    job_id = create_sync_job(account_id_obj, platform_id, "structure")

    structure_synced = False
    try:
        apply_backoff(account_id, connection_id)
        client = MetaClient(token)

        _all_statuses = json.dumps([{
            "field": "effective_status",
            "operator": "IN",
            "value": ["ACTIVE", "PAUSED", "ARCHIVED", "DELETED"],
        }])
        campaigns_data = client.paginate(
            f"/act_{ext_id}/campaigns",
            {"fields": CAMPAIGN_FIELDS, "filtering": _all_statuses, "limit": 200},
            account_id=account_id, connection_id=connection_id,
        )
        apply_backoff(account_id, connection_id)
        adsets_data = client.paginate(
            f"/act_{ext_id}/adsets",
            {"fields": ADSET_FIELDS, "filtering": _all_statuses, "limit": 200},
            account_id=account_id, connection_id=connection_id,
        )
        apply_backoff(account_id, connection_id)
        ads_data = client.paginate(
            f"/act_{ext_id}/ads",
            {"fields": AD_FIELDS, "filtering": _all_statuses, "limit": 200},
            account_id=account_id, connection_id=connection_id,
        )

        with get_worker_db() as db:
            # Upsert campaigns
            campaign_rows = []
            for c in campaigns_data:
                campaign_rows.append({
                    "account_id": account_id_obj,
                    "platform_id": platform_id,
                    "platform_campaign_id": c["id"],
                    "name": c.get("name", ""),
                    "status": STATUS_MAP.get(c.get("status", ""), "active"),
                    "effective_status": STATUS_MAP.get(c.get("effective_status", ""), "active"),
                    "objective": OBJECTIVE_MAP.get(c.get("objective", ""), c.get("objective")),
                    "platform_objective": c.get("objective"),
                    "daily_budget": _cents_to_units(c.get("daily_budget")),
                    "lifetime_budget": _cents_to_units(c.get("lifetime_budget")),
                    "buying_type": c.get("buying_type", "").lower() if c.get("buying_type") else None,
                    "start_date": _parse_date(c.get("start_time")),
                    "end_date": _parse_date(c.get("stop_time")),
                    "synced_at": datetime.now(timezone.utc),
                    "created_at": _parse_date(c.get("created_time")),
                    "updated_at": _parse_date(c.get("updated_time")),
                })

            if campaign_rows:
                stmt = pg_insert(Campaign).values(campaign_rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "platform_campaign_id"],
                    set_={
                        "name": stmt.excluded.name,
                        "status": stmt.excluded.status,
                        "effective_status": stmt.excluded.effective_status,
                        "daily_budget": stmt.excluded.daily_budget,
                        "lifetime_budget": stmt.excluded.lifetime_budget,
                        "synced_at": stmt.excluded.synced_at,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                db.execute(stmt)

            # Build campaign external_id -> internal UUID map from ALL campaigns in DB
            # (not just this batch — adsets may reference campaigns fetched in prior syncs)
            camp_rows_db = (
                db.query(Campaign)
                .filter(Campaign.account_id == account_id_obj)
                .all()
            )
            camp_id_map = {c.platform_campaign_id: c.id for c in camp_rows_db}

            # Upsert ad groups
            adgroup_rows = []
            for ag in adsets_data:
                camp_uuid = camp_id_map.get(ag.get("campaign_id"))
                if not camp_uuid:
                    continue
                adgroup_rows.append({
                    "campaign_id": camp_uuid,
                    "account_id": account_id_obj,
                    "platform_id": platform_id,
                    "platform_adgroup_id": ag["id"],
                    "name": ag.get("name", ""),
                    "status": STATUS_MAP.get(ag.get("status", ""), "active"),
                    "effective_status": STATUS_MAP.get(ag.get("effective_status", ""), "active"),
                    "optimization_goal": ag.get("optimization_goal", "").lower() if ag.get("optimization_goal") else None,
                    "billing_event": ag.get("billing_event", "").lower() if ag.get("billing_event") else None,
                    "bid_amount": _cents_to_units(ag.get("bid_amount")),
                    "daily_budget": _cents_to_units(ag.get("daily_budget")),
                    "lifetime_budget": _cents_to_units(ag.get("lifetime_budget")),
                    "targeting_summary": ag.get("targeting"),
                    "start_date": _parse_date(ag.get("start_time")),
                    "end_date": _parse_date(ag.get("stop_time")),
                    "synced_at": datetime.now(timezone.utc),
                    "created_at": _parse_date(ag.get("created_time")),
                    "updated_at": _parse_date(ag.get("updated_time")),
                })

            if adgroup_rows:
                stmt = pg_insert(AdGroup).values(adgroup_rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "platform_adgroup_id"],
                    set_={
                        "name": stmt.excluded.name,
                        "status": stmt.excluded.status,
                        "effective_status": stmt.excluded.effective_status,
                        "synced_at": stmt.excluded.synced_at,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                db.execute(stmt)

            # Build adgroup external_id -> internal UUID map
            adgroup_platform_ids = [ag["id"] for ag in adsets_data]
            adgroup_rows_db = (
                db.query(AdGroup)
                .filter(
                    AdGroup.account_id == account_id_obj,
                    AdGroup.platform_adgroup_id.in_(adgroup_platform_ids),
                )
                .all()
            )
            adgroup_id_map = {ag.platform_adgroup_id: ag.id for ag in adgroup_rows_db}

            # Upsert ads
            ad_rows = []
            for a in ads_data:
                camp_uuid = camp_id_map.get(a.get("campaign_id"))
                ag_uuid = adgroup_id_map.get(a.get("adset_id"))
                if not camp_uuid or not ag_uuid:
                    continue
                ad_rows.append({
                    "ad_group_id": ag_uuid,
                    "campaign_id": camp_uuid,
                    "account_id": account_id_obj,
                    "platform_id": platform_id,
                    "platform_ad_id": a["id"],
                    "name": a.get("name", ""),
                    "status": STATUS_MAP.get(a.get("status", ""), "active"),
                    "effective_status": STATUS_MAP.get(a.get("effective_status", ""), "active"),
                    "synced_at": datetime.now(timezone.utc),
                    "created_at": _parse_date(a.get("created_time")),
                    "updated_at": _parse_date(a.get("updated_time")),
                })

            if ad_rows:
                stmt = pg_insert(Ad).values(ad_rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "platform_ad_id"],
                    set_={
                        "name": stmt.excluded.name,
                        "status": stmt.excluded.status,
                        "effective_status": stmt.excluded.effective_status,
                        "synced_at": stmt.excluded.synced_at,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                db.execute(stmt)

        total = len(campaign_rows) + len(adgroup_rows) + len(ad_rows)
        finalize_sync_job(job_id, "completed", rows_written=total)
        # Recovery (P-2): a clean run clears any prior token alert for this
        # connection. Helper self-guards on last_error and swallows its own errors.
        from workers.token_alerts import clear_connection_token_failure
        clear_connection_token_failure(connection_id)
        logger.info(f"[{account_id}] Structure sync complete: {total} rows")
        structure_synced = True

    except RateLimitBackoff as b:
        finalize_sync_job(job_id, "skipped")
        logger.info(f"[{account_id}] Structure rescheduled in {b.countdown}s ({b.scope})")
        self.apply_async(args=[account_id], countdown=b.countdown)
        return
    except SoftTimeLimitExceeded as e:
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Structure sync exceeded soft time limit")
        return
    except MetaAPIError as e:
        if is_meta_rate_limit_error(e.code, e.subcode):
            pause_connection(connection_id, HARD_PAUSE_SECONDS)
            finalize_sync_job(job_id, "skipped")
            logger.warning(f"[{account_id}] Structure Meta rate-limit (code {e.code}) — pausing connection {HARD_PAUSE_SECONDS}s")
            self.apply_async(args=[account_id], countdown=HARD_PAUSE_SECONDS)
            return
        if e.is_auth and connection_id:
            from workers.token_alerts import alert_connection_token_failure
            alert_connection_token_failure(
                connection_id, platform_label="Meta", detail=str(e)
            )
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Structure sync failed: {e}")
        raise self.retry(exc=e)
    except Exception as e:
        finalize_sync_job(job_id, "failed", error=e)
        logger.error(f"[{account_id}] Structure sync failed: {e}")
        raise self.retry(exc=e)
    finally:
        release_lock("structure", account_id, lock_token)

    if structure_synced:
        from workers.tasks.insights import sync_insights_for_account
        from workers.tasks.async_jobs import submit_async_job_for_account
        from workers.tasks.creatives import sync_creatives_for_account
        sync_insights_for_account.delay(account_id)
        submit_async_job_for_account.delay(account_id)
        sync_creatives_for_account.delay(account_id)
