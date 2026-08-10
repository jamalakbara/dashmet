"""The one and only writer for the notifications system (P-7).

Imported by the POST endpoints and (later) by worker refresh/sync-failure
tasks — never as a side effect of a GET read. The read helpers
(``list_notifications``, ``unread_count``) are the only functions the
``GET /notifications`` endpoint touches; they emit nothing.

Dedup is enforced by the DB unique constraint ``uq_notifications_org_dedup``
on ``(organization_id, dedup_key)`` — the anti-req forbids an app-side
time-window dedup. ``create_notification`` upserts ``ON CONFLICT DO NOTHING``
so re-running a check never dupes.

Commit convention: this service flushes but does NOT commit — the caller (the
endpoint or the worker task) owns the transaction boundary, matching every
other service in ``app/services/`` (see ``accounts.py``, ``org.py``).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.notifications import Notification

# The failure classes a connection can raise for a single platform token. One
# open notification per class per connection; a recovery (refresh success or a
# reconnect) resolves all of them so an "expiring" warning and an "expired"
# error clear together (P-2). This tuple is the single source of truth — the
# worker refresh/sync-failure path (``workers/token_alerts.py``) imports it
# from here rather than re-declaring its own copy (P-7).
TOKEN_ALERT_TYPES: tuple[str, ...] = (
    "token_expired",
    "token_expiring",
    "refresh_failed",
)


def token_dedup_key(notif_type: str, connection_id: str) -> str:
    """``{type}:{connection_id}`` — one open alert per connection per class.

    THE canonical dedup-key definition for token alerts (P-7). Both the emit
    path (worker records a failure) and every clear path (refresh success,
    reconnect) derive their dedup key from this one function so they can never
    drift out of alignment. ``workers/token_alerts.py`` imports it from here.
    """
    return f"{notif_type}:{connection_id}"


def create_notification(
    db: Session,
    *,
    org_id: str,
    type: str,
    severity: str,
    title: str,
    body: str,
    dedup_key: str,
    deep_link: Optional[str] = None,
) -> Notification:
    """INSERT a notification, deduped by the DB unique constraint.

    Uses PostgreSQL ``INSERT ... ON CONFLICT (organization_id, dedup_key)``.
    On conflict the behaviour depends on the existing row's status:

    - ``resolved`` → **re-open** it (status back to ``unread``, ``resolved_at``
      cleared, title/body/severity/deep_link refreshed, ``created_at`` bumped to
      now so it sorts fresh). A condition that recurred after recovery must
      re-alert, not stay silent (P-2 alarm-when-not-fine, P-8 trace reflects
      reality).
    - ``unread`` / ``read`` → **left unchanged** (stay deduped — a failure that
      repeats every sync cycle must not spam, and a ``read`` row must not bounce
      back to ``unread``). The ``where`` predicate restricts the UPDATE to
      conflicting rows that are ``resolved``; others fall through as a no-op.

    Returns the row that now exists for ``(org_id, dedup_key)``. Does not commit
    — the caller manages the transaction.
    """
    org_uuid = uuid.UUID(org_id)
    stmt = (
        pg_insert(Notification)
        .values(
            organization_id=org_uuid,
            type=type,
            severity=severity,
            title=title,
            body=body,
            deep_link=deep_link,
            dedup_key=dedup_key,
            status="unread",
        )
        .on_conflict_do_update(
            constraint="uq_notifications_org_dedup",
            set_={
                "status": "unread",
                "resolved_at": None,
                "type": type,
                "severity": severity,
                "title": title,
                "body": body,
                "deep_link": deep_link,
                "created_at": func.now(),
            },
            where=Notification.status == "resolved",
        )
    )
    db.execute(stmt)
    db.flush()

    # Return the current row for this (org, dedup_key) — whether just inserted,
    # re-opened, or left as-is. populate_existing refreshes an already-loaded
    # identity-map instance so a re-opened row reflects its new DB state (the
    # ON CONFLICT UPDATE happens at the DB level, invisible to the ORM cache
    # otherwise). The constraint guarantees at most one row.
    return db.execute(
        select(Notification)
        .where(
            Notification.organization_id == org_uuid,
            Notification.dedup_key == dedup_key,
        )
        .execution_options(populate_existing=True)
    ).scalar_one()


def resolve_notification(
    db: Session,
    *,
    org_id: str,
    dedup_key: str,
) -> int:
    """Mark matching unresolved rows ``resolved`` (P-2 auto-clear).

    Called by the worker when a token recovers / a refresh succeeds. No-op if
    no matching unresolved row exists. Returns the number of rows resolved.
    Does not commit.
    """
    stmt = (
        update(Notification)
        .where(
            Notification.organization_id == uuid.UUID(org_id),
            Notification.dedup_key == dedup_key,
            Notification.status != "resolved",
        )
        .values(status="resolved", resolved_at=datetime.now(timezone.utc))
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount or 0


def resolve_connection_token_alerts(
    db: Session,
    *,
    org_id: str,
    connection_id: str,
) -> int:
    """Resolve every open token alert bound to one connection id.

    Marks ``resolved`` every notification whose dedup key is
    ``token_dedup_key(t, connection_id)`` for each ``t in TOKEN_ALERT_TYPES``
    — i.e. the ``token_expired`` / ``token_expiring`` / ``refresh_failed`` rows
    for this connection. Reuses ``resolve_notification`` (single writer, P-7).
    Returns the total number of rows resolved. Does not commit — the caller
    owns the transaction (service convention).
    """
    resolved = 0
    for notif_type in TOKEN_ALERT_TYPES:
        resolved += resolve_notification(
            db,
            org_id=org_id,
            dedup_key=token_dedup_key(notif_type, connection_id),
        )
    return resolved


def resolve_platform_token_alerts(
    db: Session,
    *,
    org_id: str,
    platform: str,
) -> int:
    """Clear all token alerts + health flags for an org's connections on a platform.

    The org+platform-level clear the reconnect flow needs. Reconnecting a
    platform INSERTs a brand-new ``PlatformConnection`` row (no unique
    constraint on ``(organization_id, platform_id)``), so the pre-existing
    alert's dedup key still points at the OLD, now-dead connection id. Clearing
    only the newly-created connection id would leave the old alert lit forever.

    So for every ``PlatformConnection`` in this org on this platform (old and
    new) we resolve its token alerts via ``resolve_connection_token_alerts`` and
    wipe ``last_error`` / ``last_error_at`` so the badge/banner disappears
    (P-2). Returns the total number of notifications resolved. Does not commit.

    ``platform`` is matched against ``PlatformConnection.platform_id`` verbatim
    — pass the stored id (e.g. ``"meta"``, ``"tiktok"``, ``"google_ads"``), not
    a display label.
    """
    from app.models.platform import PlatformConnection

    conns = db.execute(
        select(PlatformConnection).where(
            PlatformConnection.organization_id == uuid.UUID(org_id),
            PlatformConnection.platform_id == platform,
        )
    ).scalars().all()

    resolved = 0
    for conn in conns:
        resolved += resolve_connection_token_alerts(
            db, org_id=org_id, connection_id=str(conn.id)
        )
        conn.last_error = None
        conn.last_error_at = None
    db.flush()
    return resolved


def list_notifications(
    db: Session,
    *,
    org_id: str,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[Notification]:
    """Tenant-scoped read. Emits nothing."""
    stmt = select(Notification).where(
        Notification.organization_id == uuid.UUID(org_id)
    )
    if status is not None:
        stmt = stmt.where(Notification.status == status)
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def unread_count(db: Session, *, org_id: str) -> int:
    """Count of unread (not read, not resolved) notifications for the org."""
    from sqlalchemy import func

    stmt = select(func.count()).select_from(Notification).where(
        Notification.organization_id == uuid.UUID(org_id),
        Notification.status == "unread",
    )
    return db.execute(stmt).scalar_one()


def mark_read(
    db: Session,
    *,
    org_id: str,
    notification_id: str,
) -> Optional[Notification]:
    """Set a notification's status to ``read``, scoped to the org.

    Returns the updated row, or ``None`` if no notification with that id exists
    in this org (the endpoint turns ``None`` into a 404). Cross-org access can
    never mutate another org's row: the WHERE clause filters on
    ``organization_id`` so a foreign id simply matches nothing. Does not commit.
    """
    try:
        notif_uuid = uuid.UUID(notification_id)
    except (ValueError, AttributeError):
        return None

    notif = db.execute(
        select(Notification).where(
            Notification.id == notif_uuid,
            Notification.organization_id == uuid.UUID(org_id),
        )
    ).scalar_one_or_none()
    if notif is None:
        return None

    notif.status = "read"
    db.flush()
    return notif
