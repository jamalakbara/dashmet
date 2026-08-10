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
    from workers.rate_limit import redis_client
    from workers.token_alerts import (
        record_token_failure,
        clear_token_failure,
        send_token_failure_email,
    )
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
            client = TikTokClient(access_token="", redis_client=redis_client)
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
                    # Recovery (P-2): clear health + resolve any open alert.
                    clear_token_failure(db, connection=c)
            logger.info("Refreshed TikTok token for connection %s", conn.id)

        except (TikTokAPIError, Exception) as exc:
            logger.error("Failed to refresh TikTok token for %s: %s", conn.id, exc)
            body = (
                "Automatic refresh of your TikTok connection failed — the "
                "refresh token is likely expired or revoked. The connection has "
                "been paused. Reconnect TikTok to restore data syncing."
            )
            # Keep the existing deactivation, but add a durable trace (P-8) +
            # user-facing alert. Commit the evidence even though refresh failed.
            with get_worker_db() as db:
                c = db.get(PlatformConnection, conn.id)
                if not c:
                    continue
                c.is_active = False  # existing behavior — unlike Meta
                is_new = record_token_failure(
                    db,
                    connection=c,
                    notif_type="token_expired",
                    title="TikTok connection needs attention",
                    body=body,
                )
                should_email = is_new
            logger.warning("Deactivated connection %s — refresh token may be expired", conn.id)
            if should_email:
                with get_worker_db() as db:
                    c = db.get(PlatformConnection, conn.id)
                    if c:
                        send_token_failure_email(
                            db,
                            connection=c,
                            subject="TikTok connection needs attention",
                            body=body,
                        )
