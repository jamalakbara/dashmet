"""
Meta token refresh worker.
Runs daily at 00:45 UTC (staggered off TikTok's 00:30). Proactively exchanges
still-valid long-lived Meta tokens for fresh ones before they expire, via the
`fb_exchange_token` grant.

Meta tokens must be refreshed *while alive* — a dead token cannot be exchanged.
So this fires for connections whose `token_expires_at` falls inside a 7-day
window, well before expiry.

Failure recovery (P-5): auto-refresh cannot cover every case (revoked tokens,
the ~90d data-access ceiling, true system-user tokens). When the exchange fails
we do NOT deactivate the connection (unlike TikTok) — the token may just need a
manual re-paste, and the connection recovers on its own once re-authed. Instead
we leave a durable trace (P-8): stamp `last_error` on the connection + create a
`token_expired` notification, both committed even though the refresh failed, and
email the org owner once (deduped — no per-cycle spam).
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.meta_token_refresh.refresh_meta_tokens",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def refresh_meta_tokens(self):
    from workers.db_helpers import get_worker_db
    from app.models.platform import PlatformConnection
    from app.services.auth import decrypt_token, encrypt_token
    from workers.meta_client import MetaClient, MetaAPIError
    from workers.token_alerts import (
        record_token_failure,
        clear_token_failure,
        send_token_failure_email,
    )
    from app.config import settings

    if not (settings.META_APP_ID and settings.META_APP_SECRET):
        logger.warning(
            "META_APP_ID/META_APP_SECRET unset — cannot exchange Meta tokens, skipping refresh"
        )
        return

    cutoff = datetime.now(timezone.utc) + timedelta(days=7)

    with get_worker_db() as db:
        connections = (
            db.query(PlatformConnection)
            .filter(
                PlatformConnection.platform_id == "meta",
                PlatformConnection.is_active.is_(True),
                # NULL expiry = never-expires (true system user) or unprobed → skip.
                PlatformConnection.token_expires_at.isnot(None),
                PlatformConnection.token_expires_at < cutoff,
            )
            .all()
        )

    logger.info("Found %s Meta connections to refresh", len(connections))

    for conn in connections:
        try:
            access_token = decrypt_token(conn.access_token)
            with MetaClient(access_token) as client:
                token_data = client.exchange_long_lived_token(
                    settings.META_APP_ID, settings.META_APP_SECRET, access_token
                )
            new_access = token_data.get("access_token", "")
            expires_in = token_data.get("expires_in")
            if not new_access:
                raise ValueError("Empty access_token in fb_exchange_token response")

            with get_worker_db() as db:
                c = db.get(PlatformConnection, conn.id)
                if c:
                    c.access_token = encrypt_token(new_access)
                    if expires_in:
                        c.token_expires_at = datetime.now(timezone.utc) + timedelta(
                            seconds=int(expires_in)
                        )
                    else:
                        # Meta returned a token with no expiry → treat as
                        # never-expires. NULL the column so the refresh query's
                        # `token_expires_at IS NOT NULL` guard skips it, instead
                        # of leaving the old near-expiry value and re-exchanging
                        # this connection on every nightly run.
                        c.token_expires_at = None
                        logger.info(
                            "Meta exchange for connection %s returned no expires_in "
                            "— treating token as non-expiring (token_expires_at=NULL)",
                            conn.id,
                        )
                    # Recovery (P-2): clear health + resolve any open alert.
                    clear_token_failure(db, connection=c)
            logger.info(
                "Refreshed Meta token for connection %s (expires_in=%s)",
                conn.id,
                expires_in,
            )

        except (MetaAPIError, httpx.HTTPError, ValueError) as exc:
            # Only token/exchange-shaped failures are treated as a per-connection
            # token problem: MetaAPIError (Meta error body), httpx transport/HTTP
            # errors from the exchange call, and the ValueError we raise on an
            # empty access_token. Genuinely unexpected errors (DB down, decrypt
            # misconfig) are NOT lit as a token warning (P-2) — they fall through
            # to the retry handler below so Celery's configured backoff engages.
            logger.error("Failed to refresh Meta token for %s: %s", conn.id, exc)
            body = (
                "Automatic refresh of your Meta connection failed. The access "
                "token may be expired, revoked, or past Meta's data-access "
                "window. Reconnect Meta to restore data syncing."
            )
            # Durable trace (P-8): commit the failure evidence in its own
            # transaction even though the refresh failed. Do NOT deactivate —
            # the connection recovers on manual re-paste.
            with get_worker_db() as db:
                c = db.get(PlatformConnection, conn.id)
                if not c:
                    continue
                is_new = record_token_failure(
                    db,
                    connection=c,
                    notif_type="token_expired",
                    title="Meta connection needs attention",
                    body=body,
                )
                should_email = is_new
                email_conn = c
            if should_email:
                # Email is best-effort and outside the trace transaction — a mail
                # failure must never lose the notification. Gated by is_new so a
                # repeated failure of the same connection does not re-spam.
                with get_worker_db() as db:
                    c = db.get(PlatformConnection, conn.id)
                    if c:
                        send_token_failure_email(
                            db,
                            connection=c,
                            subject="Meta connection needs attention",
                            body=body,
                        )

        except Exception as exc:
            # Not a token failure — infra/config error (DB down, decrypt
            # misconfig, etc.). Don't stamp last_error or notify (P-2); escalate
            # to Celery's retry so the configured backoff runs instead of being
            # dead code, and the trace lives in the retry/failure record.
            logger.exception("Unexpected error refreshing Meta token for %s", conn.id)
            raise self.retry(exc=exc)
