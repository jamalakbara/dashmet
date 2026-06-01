"""
TikTok structure sync worker.
Fetches campaigns, ad groups, and ads from TikTok Business API and upserts into DB.
Schedule: every 30 minutes via Celery Beat.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TIKTOK_STATUS_MAP = {
    "STATUS_ENABLE": "active",
    "STATUS_DISABLE": "paused",
    "STATUS_DELETE": "deleted",
    "STATUS_ALL": "active",
    "CAMPAIGN_STATUS_ENABLE": "active",
    "CAMPAIGN_STATUS_DISABLE": "paused",
    "CAMPAIGN_STATUS_DELETE": "deleted",
    "ADGROUP_STATUS_ENABLE": "active",
    "ADGROUP_STATUS_DISABLE": "paused",
    "ADGROUP_STATUS_DELETE": "deleted",
    "AD_STATUS_ENABLE": "active",
    "AD_STATUS_DISABLE": "paused",
    "AD_STATUS_DELETE": "deleted",
}

TIKTOK_OBJECTIVE_MAP = {
    "CONVERSIONS": "sales",
    "TRAFFIC": "traffic",
    "APP_PROMOTION": "app_promotion",
    "REACH": "awareness",
    "VIDEO_VIEWS": "engagement",
    "ENGAGEMENT": "engagement",
    "LEAD_GENERATION": "leads",
    "CATALOG_SALES": "sales",
    "AWARENESS": "awareness",
    "SHOP_PURCHASES": "sales",
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


@celery_app.task(
    name="workers.tasks.tiktok_structure.sync_tiktok_accounts_for_connection",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_tiktok_accounts_for_connection(
    self, connection_id: str, org_id: str, advertiser_ids: list
):
    from workers.db_helpers import get_worker_db
    from app.models.platform import Account, AccountConfig, PlatformConnection
    from app.services.auth import decrypt_token
    from workers.tiktok_client import TikTokClient, TikTokAPIError

    try:
        with get_worker_db() as db:
            conn = db.get(PlatformConnection, uuid.UUID(connection_id))
            if not conn or not conn.is_active:
                return
            access_token = decrypt_token(conn.access_token)

        with TikTokClient(access_token) as client:
            advertiser_infos = client.get_advertiser_info(advertiser_ids)

        info_map = {str(a["advertiser_id"]): a for a in advertiser_infos}

        with get_worker_db() as db:
            for adv_id in advertiser_ids:
                info = info_map.get(str(adv_id), {})
                name = info.get("advertiser_name") or f"TikTok Account {adv_id}"
                currency = info.get("currency", "USD")
                timezone_str = info.get("timezone", "UTC")

                stmt = pg_insert(Account).values(
                    organization_id=uuid.UUID(org_id),
                    platform_connection_id=uuid.UUID(connection_id),
                    platform_id="tiktok",
                    external_id=str(adv_id),
                    name=name,
                    currency=currency,
                    timezone=timezone_str,
                    account_status="active",
                    synced_at=datetime.now(timezone.utc),
                ).on_conflict_do_update(
                    index_elements=["organization_id", "platform_id", "external_id"],
                    set_={
                        "name": name,
                        "currency": currency,
                        "timezone": timezone_str,
                        "synced_at": datetime.now(timezone.utc),
                    },
                )
                db.execute(stmt)
                db.flush()

                account = (
                    db.query(Account)
                    .filter(
                        Account.organization_id == uuid.UUID(org_id),
                        Account.platform_id == "tiktok",
                        Account.external_id == str(adv_id),
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
                    sync_tiktok_structure_for_account.delay(str(account.id))

        logger.info(
            "Imported %s TikTok advertiser accounts for connection %s",
            len(advertiser_ids), connection_id,
        )
    except TikTokAPIError as exc:
        logger.error("TikTok API error syncing accounts for %s: %s", connection_id, exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error syncing TikTok accounts for %s", connection_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="workers.tasks.tiktok_structure.sync_tiktok_structure_all",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_tiktok_structure_all(self):
    from workers.db_helpers import get_worker_db
    from app.models.platform import Account

    with get_worker_db() as db:
        accounts = (
            db.query(Account)
            .filter(
                Account.account_status == "active",
                Account.platform_id == "tiktok",
            )
            .all()
        )
        for account in accounts:
            sync_tiktok_structure_for_account.delay(str(account.id))
        logger.info("Enqueued TikTok structure sync for %s accounts", len(accounts))


@celery_app.task(
    name="workers.tasks.tiktok_structure.sync_tiktok_structure_for_account",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
)
def sync_tiktok_structure_for_account(self, account_id: str):
    from workers.db_helpers import get_worker_db, create_sync_job, finalize_sync_job
    from app.models.platform import Account, PlatformConnection
    from app.models.structure import Campaign, AdGroup, Ad, Creative
    from app.services.auth import decrypt_token
    from workers.tiktok_client import TikTokClient, TikTokAPIError

    account_uuid = uuid.UUID(account_id)
    job_id = create_sync_job(account_uuid, "tiktok", "structure")

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
            access_token = decrypt_token(conn.access_token)
            advertiser_id = account.external_id

        with TikTokClient(access_token) as client:
            campaigns_raw = client.get_campaigns(advertiser_id)
            adgroups_raw = client.get_adgroups(advertiser_id)
            ads_raw = client.get_ads(advertiser_id)

        now = datetime.now(timezone.utc)
        rows_written = 0

        with get_worker_db() as db:
            # --- Campaigns ---
            for c in campaigns_raw:
                platform_campaign_id = str(c["campaign_id"])
                status_raw = c.get("status") or c.get("operation_status", "")
                status = TIKTOK_STATUS_MAP.get(status_raw, "active")
                objective_raw = c.get("objective_type", "")
                objective = TIKTOK_OBJECTIVE_MAP.get(objective_raw, "awareness")
                budget_mode = c.get("budget_mode", "")
                budget = float(c.get("budget") or 0)
                daily_budget = budget if budget_mode == "BUDGET_MODE_DAY" else None
                lifetime_budget = budget if budget_mode == "BUDGET_MODE_TOTAL" else None

                stmt = pg_insert(Campaign).values(
                    account_id=account_uuid,
                    platform_id="tiktok",
                    platform_campaign_id=platform_campaign_id,
                    name=c.get("campaign_name", ""),
                    status=status,
                    effective_status=status,
                    objective=objective,
                    platform_objective=objective_raw,
                    daily_budget=daily_budget,
                    lifetime_budget=lifetime_budget,
                    synced_at=now,
                ).on_conflict_do_update(
                    index_elements=["account_id", "platform_campaign_id"],
                    set_={
                        "name": c.get("campaign_name", ""),
                        "status": status,
                        "effective_status": status,
                        "objective": objective,
                        "platform_objective": objective_raw,
                        "daily_budget": daily_budget,
                        "lifetime_budget": lifetime_budget,
                        "synced_at": now,
                    },
                )
                db.execute(stmt)
                rows_written += 1

            db.flush()

            # Build platform_campaign_id → internal UUID map
            camp_id_map: dict[str, uuid.UUID] = {
                row.platform_campaign_id: row.id
                for row in db.query(Campaign).filter(Campaign.account_id == account_uuid).all()
            }

            # --- Ad Groups ---
            for ag in adgroups_raw:
                platform_adgroup_id = str(ag["adgroup_id"])
                platform_campaign_id = str(ag.get("campaign_id", ""))
                campaign_id = camp_id_map.get(platform_campaign_id)
                if not campaign_id:
                    continue
                status_raw = ag.get("status") or ag.get("operation_status", "")
                status = TIKTOK_STATUS_MAP.get(status_raw, "active")
                budget_mode = ag.get("budget_mode", "")
                budget = float(ag.get("budget") or 0)
                daily_budget = budget if budget_mode == "BUDGET_MODE_DAY" else None
                lifetime_budget = budget if budget_mode == "BUDGET_MODE_TOTAL" else None

                stmt = pg_insert(AdGroup).values(
                    campaign_id=campaign_id,
                    account_id=account_uuid,
                    platform_id="tiktok",
                    platform_adgroup_id=platform_adgroup_id,
                    name=ag.get("adgroup_name", ""),
                    status=status,
                    effective_status=status,
                    optimization_goal=ag.get("optimization_goal"),
                    billing_event=ag.get("bid_type"),
                    bid_amount=float(ag.get("bid_price") or 0) or None,
                    daily_budget=daily_budget,
                    lifetime_budget=lifetime_budget,
                    synced_at=now,
                ).on_conflict_do_update(
                    index_elements=["account_id", "platform_adgroup_id"],
                    set_={
                        "campaign_id": campaign_id,
                        "name": ag.get("adgroup_name", ""),
                        "status": status,
                        "effective_status": status,
                        "optimization_goal": ag.get("optimization_goal"),
                        "billing_event": ag.get("bid_type"),
                        "bid_amount": float(ag.get("bid_price") or 0) or None,
                        "daily_budget": daily_budget,
                        "lifetime_budget": lifetime_budget,
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

            # --- Ads + stub Creatives ---
            for ad in ads_raw:
                platform_ad_id = str(ad["ad_id"])
                platform_adgroup_id = str(ad.get("adgroup_id", ""))
                platform_campaign_id = str(ad.get("campaign_id", ""))
                adgroup_id = adgroup_id_map.get(platform_adgroup_id)
                campaign_id = camp_id_map.get(platform_campaign_id)
                if not adgroup_id or not campaign_id:
                    continue

                status_raw = ad.get("status") or ad.get("operation_status", "")
                status = TIKTOK_STATUS_MAP.get(status_raw, "active")

                video_id = ad.get("video_id")

                # Upsert stub Creative (raw_spec holds text fields + video_id for later enrichment)
                creative_id = None
                if video_id:
                    platform_creative_id = video_id
                    raw_spec = {
                        "video_id": video_id,
                        "ad_text": ad.get("ad_text"),
                        "call_to_action": ad.get("call_to_action"),
                        "landing_page_url": ad.get("landing_page_url"),
                        "ad_format": ad.get("ad_format"),
                    }
                    stmt = pg_insert(Creative).values(
                        platform_id="tiktok",
                        account_id=account_uuid,
                        platform_creative_id=platform_creative_id,
                        format="video",
                        body=ad.get("ad_text"),
                        cta_type=ad.get("call_to_action"),
                        destination_url=ad.get("landing_page_url"),
                        raw_spec=raw_spec,
                        synced_at=now,
                    ).on_conflict_do_update(
                        index_elements=["account_id", "platform_creative_id"],
                        set_={
                            "body": ad.get("ad_text"),
                            "cta_type": ad.get("call_to_action"),
                            "destination_url": ad.get("landing_page_url"),
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
                            Creative.platform_creative_id == platform_creative_id,
                        )
                        .first()
                    )
                    if creative:
                        creative_id = creative.id

                stmt = pg_insert(Ad).values(
                    ad_group_id=adgroup_id,
                    campaign_id=campaign_id,
                    account_id=account_uuid,
                    platform_id="tiktok",
                    platform_ad_id=platform_ad_id,
                    name=ad.get("ad_name", ""),
                    status=status,
                    effective_status=status,
                    creative_id=creative_id,
                    synced_at=now,
                ).on_conflict_do_update(
                    index_elements=["account_id", "platform_ad_id"],
                    set_={
                        "name": ad.get("ad_name", ""),
                        "status": status,
                        "effective_status": status,
                        "creative_id": creative_id,
                        "synced_at": now,
                    },
                )
                db.execute(stmt)
                rows_written += 1

        finalize_sync_job(job_id, "completed", rows_written=rows_written)
        logger.info(
            "TikTok structure sync done for account %s — %s rows", account_id, rows_written
        )

        from workers.tasks.tiktok_insights import sync_tiktok_insights_for_account
        sync_tiktok_insights_for_account.delay(account_id)

    except TikTokAPIError as exc:
        logger.error("TikTok API error for account %s: %s", account_id, exc)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error in TikTok structure sync for %s", account_id)
        finalize_sync_job(job_id, "failed", error=exc)
        raise self.retry(exc=exc)
