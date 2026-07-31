"""
Google Ads creative worker.

Google ads embed their creative in the ad itself (responsive search/display text
assets), so the structure sync already populates the Creative row (title/body/
final URLs in raw_spec) — there is no separate creative object to fetch and no
external thumbnail to render. These tasks exist for chain/endpoint symmetry with
Meta/TikTok: they just ensure the Creative is present and stamped.
"""
import logging
import uuid
from datetime import datetime, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.google_creatives.sync_google_creative",
    bind=True,
    max_retries=2,
)
def sync_google_creative(self, ad_id: str):
    """Touch the ad's creative so the lazy /ads/:id/creative endpoint resolves.
    The creative content is already written by the structure sync."""
    from workers.db_helpers import get_worker_db
    from app.models.structure import Ad, Creative

    with get_worker_db() as db:
        ad = db.get(Ad, uuid.UUID(ad_id))
        if not ad or not ad.creative_id:
            return
        creative = db.get(Creative, ad.creative_id)
        if creative and not creative.synced_at:
            creative.synced_at = datetime.now(timezone.utc)


@celery_app.task(
    name="workers.tasks.google_creatives.sync_google_creatives_for_account",
    bind=True,
    max_retries=2,
)
def sync_google_creatives_for_account(self, account_id: str):
    # No-op enrichment: Google creatives are fully populated at structure time.
    logger.info("[%s] Google creatives already populated by structure sync", account_id)
