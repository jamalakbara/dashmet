"""
Google Ads structure sync worker.
Fetches campaigns, ad groups, and ads via GAQL (GoogleAdsService.search_stream)
and upserts into the normalized DB. Mirrors the Meta/TikTok structure workers
(3-phase: read-only DB → API → upsert; per-account lock + sync job + staleness).
Schedule: every 30 minutes via Celery Beat.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from workers.celery_app import celery_app, HEAVY_SOFT_TIME_LIMIT, HEAVY_TIME_LIMIT, LOCK_TTL

logger = logging.getLogger(__name__)

GOOGLE_STATUS_MAP = {
    "ENABLED": "active",
    "PAUSED": "paused",
    "REMOVED": "deleted",
    "UNKNOWN": "active",
    "UNSPECIFIED": "active",
}

# Google `advertising_channel_type` → internal objective vocabulary (types/enums.ts).
GOOGLE_OBJECTIVE_MAP = {
    "SEARCH": "traffic",
    "DISPLAY": "awareness",
    "SHOPPING": "sales",
    "VIDEO": "engagement",
    "PERFORMANCE_MAX": "sales",
    "DEMAND_GEN": "awareness",
    "MULTI_CHANNEL": "app_promotion",
    "LOCAL": "traffic",
    "SMART": "traffic",
}

# Ad type → internal creative format (types/enums.ts CreativeFormat).
GOOGLE_AD_FORMAT_MAP = {
    "RESPONSIVE_SEARCH_AD": "text",
    "EXPANDED_TEXT_AD": "text",
    "TEXT_AD": "text",
    "RESPONSIVE_DISPLAY_AD": "image",
    "IMAGE_AD": "image",
    "VIDEO_AD": "video",
    "VIDEO_RESPONSIVE_AD": "video",
}

STALE_THRESHOLD = timedelta(minutes=30)


def _is_stale(db, account_id: uuid.UUID, job_type: str) -> bool:
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
    return datetime.now(timezone.utc) - job.completed_at > STALE_THRESHOLD


def _int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _micros_to_units(value) -> float | None:
    v = _int(value)
    return v / 1_000_000 if v is not None else None


def _last_segment(resource_name) -> str:
    return str(resource_name).split("/")[-1] if resource_name else ""


@celery_app.task(
    name="workers.tasks.google_structure.sync_google_accounts_for_connection",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_google_accounts_for_connection(self, connection_id: str, org_id: str):
    from workers.db_helpers import get_worker_db
    from app.models.platform import Account, AccountConfig, PlatformConnection
    from app.services.auth import decrypt_token
    from app.config import settings
    from workers.google_client import GoogleClient, GoogleAdsClientError

    try:
        with get_worker_db() as db:
            conn = db.get(PlatformConnection, uuid.UUID(connection_id))
            if not conn or not conn.is_active:
                return
            refresh_token = decrypt_token(conn.refresh_token)

        login_cid = (settings.GOOGLE_ADS_LOGIN_CUSTOMER_ID or "").replace("-", "").strip()
        customers: list[dict] = []

        with GoogleClient(refresh_token) as client:
            if login_cid:
                # MCC configured → enumerate non-manager children of the manager.
                for row in client.list_customer_clients(login_cid):
                    if row.get("customer_client.manager"):
                        continue
                    customers.append({
                        "id": str(row.get("customer_client.id", "")),
                        "name": row.get("customer_client.descriptive_name") or "",
                        "currency": row.get("customer_client.currency_code") or "USD",
                        "timezone": row.get("customer_client.time_zone") or "UTC",
                    })
            else:
                # No MCC → treat each directly-accessible customer as a leaf account.
                for cid in client.list_accessible_customers():
                    rows = client.search(
                        cid,
                        "SELECT customer.id, customer.descriptive_name, "
                        "customer.currency_code, customer.time_zone, customer.manager "
                        "FROM customer",
                    )
                    for row in rows:
                        if row.get("customer.manager"):
                            continue
                        customers.append({
                            "id": str(row.get("customer.id", cid)),
                            "name": row.get("customer.descriptive_name") or "",
                            "currency": row.get("customer.currency_code") or "USD",
                            "timezone": row.get("customer.time_zone") or "UTC",
                        })

        # Dedup by external id.
        seen: dict[str, dict] = {}
        for c in customers:
            if c["id"]:
                seen[c["id"]] = c

        with get_worker_db() as db:
            for cid, info in seen.items():
                name = info["name"] or f"Google Ads {cid}"
                stmt = pg_insert(Account).values(
                    organization_id=uuid.UUID(org_id),
                    platform_connection_id=uuid.UUID(connection_id),
                    platform_id="google_ads",
                    external_id=cid,
                    name=name,
                    currency=info["currency"],
                    timezone=info["timezone"],
                    account_status="active",
                    synced_at=datetime.now(timezone.utc),
                ).on_conflict_do_update(
                    index_elements=["organization_id", "platform_id", "external_id"],
                    set_={
                        "name": name,
                        "currency": info["currency"],
                        "timezone": info["timezone"],
                        "account_status": "active",
                        "platform_connection_id": uuid.UUID(connection_id),
                        "synced_at": datetime.now(timezone.utc),
                    },
                )
                db.execute(stmt)
                db.flush()

                account = (
                    db.query(Account)
                    .filter(
                        Account.organization_id == uuid.UUID(org_id),
                        Account.platform_id == "google_ads",
                        Account.external_id == cid,
                    )
                    .first()
                )
                if account:
                    existing_config = (
                        db.query(AccountConfig)
                        .filter(AccountConfig.account_id == account.id)
                        .first()
                    )
                    if not existing_config:
                        db.add(AccountConfig(account_id=account.id))
                    sync_google_structure_for_account.delay(str(account.id))

        # Recovery (P-2): a clean account import clears any prior token alert for
        # this connection. Helper self-guards on last_error and swallows errors.
        from workers.token_alerts import clear_connection_token_failure
        clear_connection_token_failure(connection_id)
        logger.info(
            "Imported %s Google Ads accounts for connection %s", len(seen), connection_id
        )
    except GoogleAdsClientError as exc:
        if getattr(exc, "is_auth", False):
            # Account import is the first Google call against a connection, so a
            # revoked/expired grant surfaces here first — leave a durable token
            # trace + owner email (P-8/P-2). Additive; the retry below still runs.
            from workers.token_alerts import alert_connection_token_failure
            alert_connection_token_failure(
                connection_id, platform_label="Google Ads", detail=str(exc)
            )
        logger.error("Google API error syncing accounts for %s: %s", connection_id, exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error syncing Google accounts for %s", connection_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="workers.tasks.google_structure.sync_google_structure_all",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_google_structure_all(self):
    from workers.db_helpers import get_worker_db
    from workers.dispatch import stagger_dispatch
    from app.models.platform import Account

    with get_worker_db() as db:
        pairs = [
            (str(aid), str(cid) if cid else None)
            for aid, cid in db.query(Account.id, Account.platform_connection_id)
            .filter(Account.account_status != "disabled", Account.platform_id == "google_ads")
            .all()
        ]
    count = stagger_dispatch(sync_google_structure_for_account, pairs)
    logger.info("Enqueued Google structure sync for %s accounts", count)


@celery_app.task(
    name="workers.tasks.google_structure.sync_google_structure_for_account",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    soft_time_limit=HEAVY_SOFT_TIME_LIMIT,
    time_limit=HEAVY_TIME_LIMIT,
)
def sync_google_structure_for_account(self, account_id: str):
    from celery.exceptions import SoftTimeLimitExceeded
    from workers.db_helpers import get_worker_db, create_sync_job, finalize_sync_job
    from workers.rate_limit import acquire_lock, release_lock, pause_connection
    from app.models.platform import Account, PlatformConnection
    from app.models.structure import Campaign, AdGroup, Ad, Creative
    from app.services.auth import decrypt_token
    from workers.google_client import GoogleClient, GoogleAdsClientError

    account_uuid = uuid.UUID(account_id)

    lock_token = acquire_lock("google_structure", account_id, LOCK_TTL)
    if not lock_token:
        logger.info("Google structure already running for %s — skip", account_id)
        return

    job_id = create_sync_job(account_uuid, "google_ads", "structure")
    connection_id = None

    try:
        with get_worker_db() as db:
            account = db.get(Account, account_uuid)
            if not account:
                finalize_sync_job(job_id, "skipped")
                return

            if not _is_stale(db, account_uuid, "structure"):
                finalize_sync_job(job_id, "skipped")
                return

            conn = db.get(PlatformConnection, account.platform_connection_id)
            connection_id = str(conn.id)
            refresh_token = decrypt_token(conn.refresh_token)
            customer_id = account.external_id

        with GoogleClient(refresh_token) as client:
            campaigns_raw = client.search(
                customer_id,
                "SELECT campaign.id, campaign.name, campaign.status, "
                "campaign.advertising_channel_type, campaign_budget.amount_micros "
                "FROM campaign",
            )
            adgroups_raw = client.search(
                customer_id,
                "SELECT ad_group.id, ad_group.name, ad_group.status, campaign.id "
                "FROM ad_group",
            )
            ads_raw = client.search(
                customer_id,
                "SELECT ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.status, "
                "ad_group_ad.ad.type, ad_group_ad.ad.final_urls, "
                "ad_group_ad.ad.responsive_search_ad.headlines, "
                "ad_group_ad.ad.responsive_search_ad.descriptions, "
                "ad_group.id, campaign.id FROM ad_group_ad",
            )

        now = datetime.now(timezone.utc)
        rows_written = 0

        with get_worker_db() as db:
            # --- Campaigns ---
            for c in campaigns_raw:
                platform_campaign_id = str(c.get("campaign.id", ""))
                if not platform_campaign_id:
                    continue
                status = GOOGLE_STATUS_MAP.get(c.get("campaign.status", ""), "active")
                channel = c.get("campaign.advertising_channel_type", "")
                objective = GOOGLE_OBJECTIVE_MAP.get(channel, "traffic")
                daily_budget = _micros_to_units(c.get("campaign_budget.amount_micros"))

                stmt = pg_insert(Campaign).values(
                    account_id=account_uuid,
                    platform_id="google_ads",
                    platform_campaign_id=platform_campaign_id,
                    name=c.get("campaign.name", "") or platform_campaign_id,
                    status=status,
                    effective_status=status,
                    objective=objective,
                    platform_objective=channel,
                    daily_budget=daily_budget,
                    synced_at=now,
                ).on_conflict_do_update(
                    index_elements=["account_id", "platform_campaign_id"],
                    set_={
                        "name": c.get("campaign.name", "") or platform_campaign_id,
                        "status": status,
                        "effective_status": status,
                        "objective": objective,
                        "platform_objective": channel,
                        "daily_budget": daily_budget,
                        "synced_at": now,
                    },
                )
                db.execute(stmt)
                rows_written += 1

            db.flush()

            camp_id_map: dict[str, uuid.UUID] = {
                row.platform_campaign_id: row.id
                for row in db.query(Campaign).filter(Campaign.account_id == account_uuid).all()
            }

            # --- Ad Groups ---
            for ag in adgroups_raw:
                platform_adgroup_id = str(ag.get("ad_group.id", ""))
                platform_campaign_id = str(ag.get("campaign.id", ""))
                campaign_id = camp_id_map.get(platform_campaign_id)
                if not platform_adgroup_id or not campaign_id:
                    continue
                status = GOOGLE_STATUS_MAP.get(ag.get("ad_group.status", ""), "active")

                stmt = pg_insert(AdGroup).values(
                    campaign_id=campaign_id,
                    account_id=account_uuid,
                    platform_id="google_ads",
                    platform_adgroup_id=platform_adgroup_id,
                    name=ag.get("ad_group.name", "") or platform_adgroup_id,
                    status=status,
                    effective_status=status,
                    synced_at=now,
                ).on_conflict_do_update(
                    index_elements=["account_id", "platform_adgroup_id"],
                    set_={
                        "campaign_id": campaign_id,
                        "name": ag.get("ad_group.name", "") or platform_adgroup_id,
                        "status": status,
                        "effective_status": status,
                        "synced_at": now,
                    },
                )
                db.execute(stmt)
                rows_written += 1

            db.flush()

            adgroup_id_map: dict[str, uuid.UUID] = {
                row.platform_adgroup_id: row.id
                for row in db.query(AdGroup).filter(AdGroup.account_id == account_uuid).all()
            }

            # --- Ads + Creatives (Google ads embed their creative — ad id == creative id) ---
            for ad in ads_raw:
                platform_ad_id = str(ad.get("ad_group_ad.ad.id", ""))
                platform_adgroup_id = str(ad.get("ad_group.id", ""))
                platform_campaign_id = str(ad.get("campaign.id", ""))
                adgroup_id = adgroup_id_map.get(platform_adgroup_id)
                campaign_id = camp_id_map.get(platform_campaign_id)
                if not platform_ad_id or not adgroup_id or not campaign_id:
                    continue

                status = GOOGLE_STATUS_MAP.get(ad.get("ad_group_ad.status", ""), "active")
                ad_type = ad.get("ad_group_ad.ad.type", "")
                fmt = GOOGLE_AD_FORMAT_MAP.get(ad_type, "text")

                headlines = [
                    h.get("text") for h in (ad.get("ad_group_ad.ad.responsive_search_ad.headlines") or [])
                    if isinstance(h, dict) and h.get("text")
                ]
                descriptions = [
                    d.get("text") for d in (ad.get("ad_group_ad.ad.responsive_search_ad.descriptions") or [])
                    if isinstance(d, dict) and d.get("text")
                ]
                final_urls = ad.get("ad_group_ad.ad.final_urls") or []
                ad_name = ad.get("ad_group_ad.ad.name") or (headlines[0] if headlines else f"Ad {platform_ad_id}")

                raw_spec = {
                    "ad_type": ad_type,
                    "headlines": headlines,
                    "descriptions": descriptions,
                    "final_urls": final_urls,
                }
                stmt = pg_insert(Creative).values(
                    platform_id="google_ads",
                    account_id=account_uuid,
                    platform_creative_id=platform_ad_id,
                    format=fmt,
                    title=headlines[0] if headlines else None,
                    body=descriptions[0] if descriptions else None,
                    destination_url=final_urls[0] if final_urls else None,
                    raw_spec=raw_spec,
                    synced_at=now,
                ).on_conflict_do_update(
                    index_elements=["account_id", "platform_creative_id"],
                    set_={
                        "format": fmt,
                        "title": headlines[0] if headlines else None,
                        "body": descriptions[0] if descriptions else None,
                        "destination_url": final_urls[0] if final_urls else None,
                        "raw_spec": raw_spec,
                        "synced_at": now,
                    },
                )
                db.execute(stmt)
                db.flush()
                creative = (
                    db.query(Creative)
                    .filter(
                        Creative.account_id == account_uuid,
                        Creative.platform_creative_id == platform_ad_id,
                    )
                    .first()
                )
                creative_id = creative.id if creative else None

                stmt = pg_insert(Ad).values(
                    ad_group_id=adgroup_id,
                    campaign_id=campaign_id,
                    account_id=account_uuid,
                    platform_id="google_ads",
                    platform_ad_id=platform_ad_id,
                    name=ad_name,
                    status=status,
                    effective_status=status,
                    creative_id=creative_id,
                    synced_at=now,
                ).on_conflict_do_update(
                    index_elements=["account_id", "platform_ad_id"],
                    set_={
                        "name": ad_name,
                        "status": status,
                        "effective_status": status,
                        "creative_id": creative_id,
                        "synced_at": now,
                    },
                )
                db.execute(stmt)
                rows_written += 1

        finalize_sync_job(job_id, "completed", rows_written=rows_written)
        # Recovery (P-2): a clean run clears any prior token alert for this
        # connection. Helper self-guards on last_error and swallows its own errors.
        if connection_id:
            from workers.token_alerts import clear_connection_token_failure
            clear_connection_token_failure(connection_id)
        logger.info(
            "Google structure sync done for account %s — %s rows", account_id, rows_written
        )

        from workers.tasks.google_insights import sync_google_insights_for_account
        from workers.tasks.google_creatives import sync_google_creatives_for_account
        sync_google_insights_for_account.delay(account_id)
        sync_google_insights_for_account.delay(account_id, "last_30d", "insights_historical")
        sync_google_creatives_for_account.delay(account_id)

    except SoftTimeLimitExceeded as exc:
        logger.error("Google structure sync for %s exceeded soft time limit", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        return
    except GoogleAdsClientError as exc:
        # Quota errors pause the shared connection (non-blocking) and reschedule
        # off the retry budget; other API errors go through normal retry.
        if exc.is_quota:
            if connection_id:
                pause_connection(connection_id, 300)
            logger.warning("Google quota hit for %s — rescheduling structure in 300s", account_id)
            finalize_sync_job(job_id, "skipped")
            self.apply_async(args=[account_id], countdown=300)
            return
        if exc.is_auth and connection_id:
            # Durable token-failure trace + owner email (P-8/P-2). Still fails
            # the sync_job below — the alert is additive, not a swallow.
            from workers.token_alerts import alert_connection_token_failure
            alert_connection_token_failure(
                connection_id, platform_label="Google Ads", detail=str(exc)
            )
        logger.error("Google API error for account %s: %s", account_id, exc)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error in Google structure sync for %s", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    finally:
        release_lock("google_structure", account_id, lock_token)
