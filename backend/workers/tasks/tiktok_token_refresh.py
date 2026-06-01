"""
TikTok token refresh worker.
Runs daily at 00:30 UTC. Refreshes access tokens before they expire (24h lifetime).
"""
import logging
from datetime import datetime, timedelta, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.tiktok_token_refresh.refresh_tiktok_tokens",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def refresh_tiktok_tokens(self):
    from workers.db_helpers import get_worker_db
    from app.models.platform import PlatformConnection
    from app.services.auth import decrypt_token, encrypt_token
    from workers.tiktok_client import TikTokClient, TikTokAPIError
    from app.config import settings

    cutoff = datetime.now(timezone.utc) + timedelta(hours=2)

    with get_worker_db() as db:
        connections = (
            db.query(PlatformConnection)
            .filter(
                PlatformConnection.platform_id == "tiktok",
                PlatformConnection.is_active.is_(True),
                PlatformConnection.token_expires_at.isnot(None),
                PlatformConnection.token_expires_at < cutoff,
            )
            .all()
        )

    logger.info("Found %s TikTok connections to refresh", len(connections))

    for conn in connections:
        try:
            refresh_token = decrypt_token(conn.refresh_token)
            client = TikTokClient(access_token="")
            token_data = client.refresh_access_token(
                settings.TIKTOK_APP_ID, settings.TIKTOK_APP_SECRET, refresh_token
            )
            new_access = token_data.get("access_token", "")
            expires_in = token_data.get("expires_in", 86400)
            if not new_access:
                raise ValueError("Empty access_token in refresh response")

            with get_worker_db() as db:
                c = db.get(PlatformConnection, conn.id)
                if c:
                    c.access_token = encrypt_token(new_access)
                    c.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            logger.info("Refreshed TikTok token for connection %s", conn.id)

        except (TikTokAPIError, Exception) as exc:
            logger.error("Failed to refresh TikTok token for %s: %s", conn.id, exc)
            with get_worker_db() as db:
                c = db.get(PlatformConnection, conn.id)
                if c:
                    c.is_active = False
            logger.warning("Deactivated connection %s — refresh token may be expired", conn.id)
