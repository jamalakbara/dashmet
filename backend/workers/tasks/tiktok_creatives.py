"""
TikTok creative sync worker.
Enriches stub Creative records with video metadata (thumbnail, preview URL).
Triggered lazily when user views an ad detail in the dashboard.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

CREATIVE_TTL = timedelta(hours=1)


def _creative_is_fresh(creative) -> bool:
    if not creative or not creative.synced_at or not creative.thumbnail_url:
        return False
    return datetime.now(timezone.utc) - creative.synced_at < CREATIVE_TTL


@celery_app.task(
    name="workers.tasks.tiktok_creatives.sync_tiktok_creative",
    bind=True,
    max_retries=3,
    retry_backoff=True,
)
def sync_tiktok_creative(self, ad_id: str):
    from workers.db_helpers import get_worker_db
    from app.models.platform import Account, PlatformConnection
    from app.models.structure import Ad, Creative
    from app.services.auth import decrypt_token
    from workers.tiktok_client import TikTokClient, TikTokAPIError
    from workers.rate_limit import redis_client

    ad_uuid = uuid.UUID(ad_id)

    try:
        with get_worker_db() as db:
            ad = db.get(Ad, ad_uuid)
            if not ad:
                return

            # Check if creative is already fresh
            if ad.creative_id:
                creative = db.get(Creative, ad.creative_id)
                if _creative_is_fresh(creative):
                    return

            account = db.get(Account, ad.account_id)
            conn = db.get(PlatformConnection, account.platform_connection_id)
            access_token = decrypt_token(conn.access_token)
            advertiser_id = account.external_id

            # Get video_id from the stub creative's raw_spec
            if ad.creative_id:
                creative = db.get(Creative, ad.creative_id)
                raw_spec = creative.raw_spec or {} if creative else {}
            else:
                raw_spec = {}

            video_id = raw_spec.get("video_id")
            tiktok_item_id = raw_spec.get("tiktok_item_id")
            if not video_id and not tiktok_item_id:
                return

        cover_url = None
        preview_url = None
        video_name = None

        if video_id:
            with TikTokClient(access_token, redis_client=redis_client) as client:
                video_infos = client.get_video_info(advertiser_id, [video_id])
            if video_infos:
                video = video_infos[0]
                cover_url = video.get("cover_url")
                preview_url = video.get("preview_url")
                video_name = video.get("video_name")
        elif tiktok_item_id:
            import httpx
            try:
                resp = httpx.get(
                    "https://www.tiktok.com/oembed",
                    params={"url": f"https://www.tiktok.com/video/{tiktok_item_id}"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                oembed = resp.json()
                cover_url = oembed.get("thumbnail_url")
                video_name = oembed.get("title")
            except Exception as exc:
                logger.warning("oEmbed fetch failed for item %s: %s", tiktok_item_id, exc)
        now = datetime.now(timezone.utc)

        with get_worker_db() as db:
            ad = db.get(Ad, ad_uuid)
            if not ad:
                return

            if ad.creative_id:
                creative = db.get(Creative, ad.creative_id)
            else:
                creative = None

            if creative:
                creative.thumbnail_url = cover_url
                creative.video_id = preview_url
                if video_name and not creative.title:
                    creative.title = video_name
                creative.synced_at = now
            else:
                # Shouldn't happen after structure sync, but handle gracefully
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                from app.models.structure import Creative as CreativeModel
                stmt = pg_insert(CreativeModel).values(
                    platform_id="tiktok",
                    account_id=ad.account_id,
                    platform_creative_id=video_id,
                    format="video",
                    title=video_name,
                    thumbnail_url=cover_url,
                    video_id=preview_url,
                    body=raw_spec.get("ad_text"),
                    cta_type=raw_spec.get("call_to_action"),
                    destination_url=raw_spec.get("landing_page_url"),
                    raw_spec=raw_spec,
                    synced_at=now,
                ).on_conflict_do_update(
                    index_elements=["account_id", "platform_creative_id"],
                    set_={
                        "thumbnail_url": cover_url,
                        "video_id": preview_url,
                        "title": video_name,
                        "synced_at": now,
                    },
                )
                db.execute(stmt)
                db.flush()
                new_creative = (
                    db.query(Creative)
                    .filter(
                        Creative.account_id == ad.account_id,
                        Creative.platform_creative_id == video_id,
                    )
                    .first()
                )
                if new_creative:
                    db.get(Ad, ad_uuid).creative_id = new_creative.id

        logger.info("TikTok creative enriched for ad %s (video %s)", ad_id, video_id)

    except TikTokAPIError as exc:
        logger.error("TikTok API error fetching creative for ad %s: %s", ad_id, exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Unexpected error fetching TikTok creative for ad %s", ad_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="workers.tasks.tiktok_creatives.sync_tiktok_creatives_for_account",
    bind=True,
    max_retries=3,
)
def sync_tiktok_creatives_for_account(self, account_id: str):
    from workers.db_helpers import get_worker_db
    from app.models.structure import Ad, Creative

    with get_worker_db() as db:
        ads = (
            db.query(Ad)
            .filter(Ad.account_id == uuid.UUID(account_id), Ad.creative_id.isnot(None))
            .all()
        )
        stale_ad_ids = []
        for ad in ads:
            creative = db.get(Creative, ad.creative_id)
            if not _creative_is_fresh(creative):
                stale_ad_ids.append(str(ad.id))

    for ad_id in stale_ad_ids:
        sync_tiktok_creative.delay(ad_id)

    logger.info(
        "[%s] Enqueued %s stale TikTok creative syncs", account_id, len(stale_ad_ids)
    )
