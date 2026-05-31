"""
Sync worker — Creatives
Fetches ad creative content lazily (triggered when user views an ad).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

CREATIVE_FIELDS = (
    "id,name,title,body,image_url,thumbnail_url,"
    "video_id,call_to_action_type,"
    "object_story_spec,asset_feed_spec"
)


def _creative_is_fresh(creative, ttl_minutes: int = 60) -> bool:
    if not creative or not creative.synced_at:
        return False
    synced = creative.synced_at
    if not synced.tzinfo:
        synced = synced.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - synced) < timedelta(minutes=ttl_minutes)


def _infer_format(raw: dict) -> str:
    if raw.get("video_id"):
        return "video"
    obj_spec = raw.get("object_story_spec", {})
    if obj_spec:
        if "video_data" in obj_spec:
            return "video"
        if "link_data" in obj_spec:
            if obj_spec.get("link_data", {}).get("child_attachments"):
                return "carousel"
    if raw.get("image_url"):
        return "image"
    return "text"


@celery_app.task(
    name="workers.tasks.creatives.sync_creative",
    bind=True,
    max_retries=3,
    retry_backoff=True,
)
def sync_creative(self, ad_id: str):
    from workers.db_helpers import get_worker_db
    from workers.meta_client import MetaClient
    from workers.rate_limit import apply_backoff
    from app.models.platform import Account, PlatformConnection
    from app.models.structure import Ad, Creative
    from app.services.auth import decrypt_token
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    with get_worker_db() as db:
        ad = db.query(Ad).filter(Ad.id == uuid.UUID(ad_id)).first()
        if not ad:
            return

        if ad.creative and _creative_is_fresh(ad.creative):
            logger.info(f"[{ad_id}] Creative fresh — skip")
            return

        account = db.get(Account, ad.account_id)
        conn = db.get(PlatformConnection, account.platform_connection_id)
        if not conn or not conn.is_active:
            return

        token = decrypt_token(conn.access_token)
        apply_backoff(str(ad.account_id))

        try:
            client = MetaClient(token)

            raw_ad_data, _ = client.get(
                f"/{ad.platform_ad_id}",
                {"fields": "creative{id}"},
            )
            creative_ref = raw_ad_data.get("creative", {})
            creative_platform_id = creative_ref.get("id") if creative_ref else None

            if not creative_platform_id:
                logger.warning(f"[{ad_id}] No creative ID found on ad")
                return

            raw, _ = client.get(f"/{creative_platform_id}", {"fields": CREATIVE_FIELDS})

            cta = raw.get("call_to_action_type", "")
            destination_url = None
            obj_spec = raw.get("object_story_spec", {})
            if obj_spec:
                link_data = obj_spec.get("link_data", {})
                destination_url = link_data.get("link")

            creative_row = {
                "platform_id": account.platform_id,
                "account_id": account.id,
                "platform_creative_id": creative_platform_id,
                "name": raw.get("name"),
                "format": _infer_format(raw),
                "title": raw.get("title"),
                "body": raw.get("body"),
                "image_url": raw.get("image_url"),
                "thumbnail_url": raw.get("thumbnail_url"),
                "video_id": raw.get("video_id"),
                "cta_type": cta.lower() if cta else None,
                "destination_url": destination_url,
                "raw_spec": raw.get("object_story_spec") or raw.get("asset_feed_spec"),
                "synced_at": datetime.now(timezone.utc),
            }

            stmt = pg_insert(Creative).values([creative_row])
            stmt = stmt.on_conflict_do_update(
                index_elements=["account_id", "platform_creative_id"],
                set_={
                    "title": stmt.excluded.title,
                    "body": stmt.excluded.body,
                    "image_url": stmt.excluded.image_url,
                    "thumbnail_url": stmt.excluded.thumbnail_url,
                    "cta_type": stmt.excluded.cta_type,
                    "destination_url": stmt.excluded.destination_url,
                    "raw_spec": stmt.excluded.raw_spec,
                    "synced_at": stmt.excluded.synced_at,
                },
            )
            db.execute(stmt)

            creative_obj = (
                db.query(Creative)
                .filter(
                    Creative.account_id == account.id,
                    Creative.platform_creative_id == creative_platform_id,
                )
                .first()
            )
            if creative_obj:
                db.execute(
                    update(Ad).where(Ad.id == ad.id).values(creative_id=creative_obj.id)
                )

            logger.info(f"[{ad_id}] Creative synced: {creative_platform_id}")

        except Exception as e:
            logger.error(f"[{ad_id}] Creative sync failed: {e}")
            raise self.retry(exc=e)
