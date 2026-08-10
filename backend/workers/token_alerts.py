"""Shared token-failure alerting for the refresh/sync worker paths.

One emission path for all platforms (P-7): Meta refresh, TikTok refresh, and
Google sync-auth failures all funnel through here rather than each hand-rolling
its own notification write. The single writer underneath is
``app/services/notifications.py`` — this module never touches the notifications
table directly.

Two responsibilities, both durable-trace oriented (P-8):
- ``record_token_failure`` — stamp ``last_error``/``last_error_at`` on the
  connection and upsert a deduped notification. Returns whether the
  notification was *newly created* so the caller can gate email (don't re-spam
  when the ON CONFLICT hit an already-unresolved row).
- ``clear_token_failure`` — on recovery, clear ``last_error`` and resolve the
  matching notifications so the badge/banner auto-disappears (P-2).

The dedup key scheme is ``{type}:{connection_id}`` — one open alert per
connection per failure class, deduped by the DB unique constraint on
``(organization_id, dedup_key)``.

Callers own the transaction: these functions flush (via the notifications
service) but do not commit. The task commits the trace itself so it survives
even when the data path rolls back.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notifications import Notification
from app.services.notifications import (
    TOKEN_ALERT_TYPES,
    create_notification,
    resolve_notification,
    token_dedup_key,
)

logger = logging.getLogger(__name__)

DEEP_LINK_CONNECTIONS = "/settings/connections"


def _has_open_notification(db: Session, *, org_id, dedup_key: str) -> bool:
    """True if an unresolved notification already exists for this (org, key).

    Used to gate email: create_notification's ON CONFLICT DO NOTHING can't tell
    us whether it inserted or hit an existing row, so we check first."""
    row = db.execute(
        select(Notification.id).where(
            Notification.organization_id == org_id,
            Notification.dedup_key == dedup_key,
            Notification.status != "resolved",
        )
    ).first()
    return row is not None


def record_token_failure(
    db: Session,
    *,
    connection,
    notif_type: str,
    title: str,
    body: str,
) -> bool:
    """Stamp the connection's health fields + emit a deduped notification.

    Returns True when the notification is *newly created* (no prior unresolved
    row existed) — the caller uses this to decide whether to send an email, so a
    repeated failure of the same connection does not re-email every cycle.

    Does not commit; the caller owns the transaction (and should commit the
    trace even if the surrounding data path fails — P-8)."""
    org_id = connection.organization_id
    connection_id = str(connection.id)
    dedup_key = token_dedup_key(notif_type, connection_id)

    connection.last_error = (body or "")[:2000]
    connection.last_error_at = datetime.now(timezone.utc)

    is_new = not _has_open_notification(db, org_id=org_id, dedup_key=dedup_key)

    create_notification(
        db,
        org_id=str(org_id),
        type=notif_type,
        severity="error",
        title=title,
        body=body,
        dedup_key=dedup_key,
        deep_link=DEEP_LINK_CONNECTIONS,
    )
    return is_new


def clear_token_failure(
    db: Session,
    *,
    connection,
    notif_types: tuple[str, ...] = TOKEN_ALERT_TYPES,
) -> None:
    """Recovery path (P-2): clear health fields + resolve matching notifications.

    Resolves every failure class we might have raised for this connection so a
    single successful refresh clears both an "expiring" warning and an "expired"
    error. Does not commit."""
    connection.last_error = None
    connection.last_error_at = None
    connection_id = str(connection.id)
    for notif_type in notif_types:
        resolve_notification(
            db,
            org_id=str(connection.organization_id),
            dedup_key=token_dedup_key(notif_type, connection_id),
        )


def alert_connection_token_failure(
    connection_id: str,
    *,
    platform_label: str,
    notif_type: str = "token_expired",
    detail: str | None = None,
) -> None:
    """One-shot durable alert for a sync-time auth failure (P-8 + P-2 email gate).

    Opens its own committed transaction so the trace survives regardless of the
    caller's sync_job rollback, then emails the org owner once (gated on the
    notification being newly created). Safe to call from any Google sync task's
    ``except`` block — swallows its own errors so alerting never masks the
    original sync failure the caller is about to re-raise.

    The ``connection_id`` is resolved to the live ``PlatformConnection`` inside
    the fresh session; a missing connection is a no-op."""
    from workers.db_helpers import get_worker_db
    from app.models.platform import PlatformConnection

    title = f"{platform_label} connection needs attention"
    body = (
        f"{platform_label} sync failed to authenticate — the OAuth token is "
        f"likely expired or revoked. Reconnect {platform_label} to restore data "
        f"syncing."
    )
    if detail:
        body = f"{body} ({detail[:300]})"

    try:
        import uuid as _uuid

        with get_worker_db() as db:
            conn = db.get(PlatformConnection, _uuid.UUID(str(connection_id)))
            if not conn:
                return
            is_new = record_token_failure(
                db,
                connection=conn,
                notif_type=notif_type,
                title=title,
                body=body,
            )
            should_email = is_new
        if should_email:
            with get_worker_db() as db:
                conn = db.get(PlatformConnection, _uuid.UUID(str(connection_id)))
                if conn:
                    send_token_failure_email(
                        db, connection=conn, subject=title, body=body
                    )
    except Exception:  # noqa: BLE001 — alerting must never mask the sync error
        logger.exception(
            "Failed to record token-failure alert for connection %s", connection_id
        )


def clear_connection_token_failure(connection_id: str) -> None:
    """Recovery one-shot for a sync SUCCESS path (P-2 auto-clear, P-7 one writer).

    Opens its own committed transaction, re-fetches the live
    ``PlatformConnection``, and — ONLY if it was previously in a failed state
    (``last_error is not None``) — funnels through ``clear_token_failure`` to
    resolve its open token alerts and wipe ``last_error``/``last_error_at``. The
    guard keeps a healthy connection's success path free of a pointless resolve
    query every cycle (P-2: silent when everything is fine).

    Safe to call at any sync task's success/completion site: it swallows and
    logs its own errors so clearing a stale alert can never fail a sync that
    otherwise succeeded. A missing connection is a no-op. Goes through
    ``clear_token_failure`` — never touches the notifications table directly."""
    from workers.db_helpers import get_worker_db
    from app.models.platform import PlatformConnection

    try:
        import uuid as _uuid

        with get_worker_db() as db:
            conn = db.get(PlatformConnection, _uuid.UUID(str(connection_id)))
            if conn is None or conn.last_error is None:
                return
            clear_token_failure(db, connection=conn)
    except Exception:  # noqa: BLE001 — clearing must never fail a successful sync
        logger.exception(
            "Failed to clear token-failure alert for connection %s", connection_id
        )


def send_token_failure_email(db: Session, *, connection, subject: str, body: str) -> None:
    """Best-effort email to the org owner on a token failure.

    Emailing must never crash the refresh/sync task or gate the durable trace —
    the DB notification is the source of truth (same contract as
    ``app/services/email.py``'s post-commit sends). Any transport error is
    logged and swallowed here; the notification row still stands."""
    from app.models.auth import User, OrganizationMembership
    from app.services.email import _send, _email_configured, EmailError

    if not _email_configured():
        logger.info(
            "[DEV] email not configured — token-failure alert for connection %s: %s",
            connection.id,
            subject,
        )
        return

    # Owner(s) of the org own connection health — notify them.
    recipients = db.execute(
        select(User.email)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(
            OrganizationMembership.organization_id == connection.organization_id,
            OrganizationMembership.role == "owner",
        )
    ).scalars().all()

    html_body = (
        f'<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;color:#1f2937">'
        f'<h2 style="margin:0 0 8px">{subject}</h2>'
        f'<p style="margin:0 0 16px;color:#4b5563">{body}</p>'
        f'<p style="margin:0 0 24px">'
        f'<a href="{DEEP_LINK_CONNECTIONS}" '
        f'style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;'
        f'padding:10px 20px;border-radius:8px;font-weight:600">Review connections</a></p>'
        f'</div>'
    )
    for to in recipients:
        try:
            _send(to, subject, body, html_body)
            logger.info("Token-failure email sent to %s for connection %s", to, connection.id)
        except EmailError as exc:
            logger.error("Failed to send token-failure email to %s: %s", to, exc)
