"""Notification writer + endpoint invariants.

Covers the four things the plan (§Tests) and the rules call out:
- dedup idempotency (DB unique constraint, not an app-side time window)
- resolve sets status + resolved_at (P-2 auto-clear)
- tenant isolation on GET /notifications and POST /notifications/{id}/read
- no-emit-from-GET (structural: the read path inserts zero rows)

Endpoint behavior is exercised by calling the route functions directly with a
seeded current_user dict + the test `db` session — the same style as
test_account_access.py::test_insights_resolver_enforces_member_grant.
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.api.v1.endpoints.notifications import (
    list_notifications as list_endpoint,
    mark_notification_read as read_endpoint,
)
from app.models.notifications import Notification
from app.models.platform import PlatformConnection
from app.services import notifications as notif_svc
from tests.conftest import make_org


def _cu(org_id, role="owner"):
    return {
        "user_id": str(uuid.uuid4()),
        "org_id": org_id,
        "role": role,
        "email": "x@x.co",
    }


def _count_rows(db, org_id=None) -> int:
    stmt = select(func.count()).select_from(Notification)
    if org_id is not None:
        stmt = stmt.where(Notification.organization_id == uuid.UUID(org_id))
    return db.execute(stmt).scalar_one()


# ── dedup idempotency ────────────────────────────────────────────────────────

def test_create_notification_deduped_by_db_constraint(db):
    org_id = make_org(db)
    db.flush()

    kwargs = dict(
        org_id=org_id,
        type="token_expired",
        severity="error",
        title="Meta token expired",
        body="Reconnect Meta.",
        dedup_key="token_expired:conn-123",
        deep_link="/settings/connections",
    )
    first = notif_svc.create_notification(db, **kwargs)
    second = notif_svc.create_notification(db, **kwargs)

    # Exactly one row, and both calls resolve to the same (pre-existing) row.
    assert _count_rows(db, org_id) == 1
    assert first.id == second.id


def test_same_dedup_key_across_orgs_is_two_rows(db):
    """The constraint is (organization_id, dedup_key) — same key in different
    orgs is not a collision (tenant isolation of dedup)."""
    org_a = make_org(db, name="A")
    org_b = make_org(db, name="B")
    db.flush()

    key = "token_expired:conn-x"
    a = notif_svc.create_notification(
        db, org_id=org_a, type="token_expired", severity="error",
        title="t", body="b", dedup_key=key,
    )
    b = notif_svc.create_notification(
        db, org_id=org_b, type="token_expired", severity="error",
        title="t", body="b", dedup_key=key,
    )
    assert a.id != b.id
    assert _count_rows(db, org_a) == 1
    assert _count_rows(db, org_b) == 1


# ── resolve (P-2 auto-clear) ─────────────────────────────────────────────────

def test_resolve_sets_status_and_resolved_at(db):
    org_id = make_org(db)
    db.flush()
    n = notif_svc.create_notification(
        db, org_id=org_id, type="refresh_failed", severity="error",
        title="t", body="b", dedup_key="refresh_failed:c1",
    )
    assert n.status == "unread"
    assert n.resolved_at is None

    resolved = notif_svc.resolve_notification(
        db, org_id=org_id, dedup_key="refresh_failed:c1"
    )
    assert resolved == 1
    db.refresh(n)
    assert n.status == "resolved"
    assert n.resolved_at is not None


def test_resolve_is_noop_when_nothing_matches(db):
    org_id = make_org(db)
    db.flush()
    assert notif_svc.resolve_notification(
        db, org_id=org_id, dedup_key="nope"
    ) == 0


def test_recreate_after_resolve_reopens_same_row(db):
    """A recurrence after recovery re-opens the resolved row rather than staying
    silent (P-2/P-8). Same (org, dedup_key) slot — still exactly one row, but
    status is back to unread, resolved_at cleared, created_at bumped, and the
    body refreshed to the new failure's text."""
    org_id = make_org(db)
    db.flush()
    first = notif_svc.create_notification(
        db, org_id=org_id, type="token_expired", severity="error",
        title="t", body="old body", dedup_key="token_expired:c9",
    )
    old_created = first.created_at
    notif_svc.resolve_notification(db, org_id=org_id, dedup_key="token_expired:c9")
    db.refresh(first)
    assert first.status == "resolved"

    reopened = notif_svc.create_notification(
        db, org_id=org_id, type="token_expired", severity="error",
        title="t", body="new body", dedup_key="token_expired:c9",
    )
    assert _count_rows(db, org_id) == 1
    assert reopened.id == first.id
    assert reopened.status == "unread"
    assert reopened.resolved_at is None
    assert reopened.body == "new body"
    assert reopened.created_at >= old_created


def test_recreate_while_open_does_not_dupe_or_reset(db):
    """While a row is still open, re-running the check must not dupe, and must
    not bounce a *read* row back to unread (only resolved rows re-open)."""
    org_id = make_org(db)
    db.flush()
    kwargs = dict(
        org_id=org_id, type="token_expired", severity="error",
        title="t", body="b", dedup_key="token_expired:c8",
    )
    n = notif_svc.create_notification(db, **kwargs)
    notif_svc.mark_read(db, org_id=org_id, notification_id=str(n.id))
    db.refresh(n)
    assert n.status == "read"

    notif_svc.create_notification(db, **kwargs)
    db.refresh(n)
    assert _count_rows(db, org_id) == 1
    assert n.status == "read"  # not reset to unread


# ── read helpers ─────────────────────────────────────────────────────────────

def test_unread_count_excludes_read_and_resolved(db):
    org_id = make_org(db)
    db.flush()
    notif_svc.create_notification(
        db, org_id=org_id, type="a", severity="info", title="t", body="b",
        dedup_key="k1",
    )
    n2 = notif_svc.create_notification(
        db, org_id=org_id, type="b", severity="info", title="t", body="b",
        dedup_key="k2",
    )
    notif_svc.mark_read(db, org_id=org_id, notification_id=str(n2.id))
    assert notif_svc.unread_count(db, org_id=org_id) == 1


# ── tenant isolation: mark_read ──────────────────────────────────────────────

def test_mark_read_cross_org_returns_none(db):
    org_a = make_org(db, name="A")
    org_b = make_org(db, name="B")
    db.flush()
    n = notif_svc.create_notification(
        db, org_id=org_a, type="a", severity="info", title="t", body="b",
        dedup_key="k",
    )
    # Org B cannot read/mutate org A's notification.
    assert notif_svc.mark_read(
        db, org_id=org_b, notification_id=str(n.id)
    ) is None
    db.refresh(n)
    assert n.status == "unread"  # untouched


def test_read_endpoint_cross_org_404(db):
    org_a = make_org(db, name="A")
    org_b = make_org(db, name="B")
    db.flush()
    n = notif_svc.create_notification(
        db, org_id=org_a, type="a", severity="info", title="t", body="b",
        dedup_key="k",
    )
    with pytest.raises(HTTPException) as ei:
        read_endpoint(str(n.id), _cu(org_b), db)
    assert ei.value.status_code == 404


def test_read_endpoint_unknown_id_404(db):
    org_id = make_org(db)
    db.flush()
    with pytest.raises(HTTPException) as ei:
        read_endpoint(str(uuid.uuid4()), _cu(org_id), db)
    assert ei.value.status_code == 404


# ── tenant isolation + no-emit-from-GET: list endpoint ───────────────────────

def test_list_endpoint_is_tenant_scoped(db):
    org_a = make_org(db, name="A")
    org_b = make_org(db, name="B")
    db.flush()
    notif_svc.create_notification(
        db, org_id=org_a, type="a", severity="info", title="A-only", body="b",
        dedup_key="ka",
    )
    notif_svc.create_notification(
        db, org_id=org_b, type="b", severity="info", title="B-only", body="b",
        dedup_key="kb",
    )

    resp_a = list_endpoint(_cu(org_a), db, status=None)
    titles_a = [i.title for i in resp_a.data.items]
    assert titles_a == ["A-only"]
    assert resp_a.data.unread_count == 1


def test_get_emits_nothing(db):
    """Structural: GET /notifications must never create a row (anti-req: no
    notification as a side effect of a read)."""
    org_id = make_org(db)
    db.flush()
    notif_svc.create_notification(
        db, org_id=org_id, type="a", severity="info", title="t", body="b",
        dedup_key="k",
    )
    before = _count_rows(db)

    list_endpoint(_cu(org_id), db, status=None)
    list_endpoint(_cu(org_id), db, status="unread")
    db.flush()

    assert _count_rows(db) == before


# ── reconnect clears token alerts (org+platform level) ───────────────────────

def _make_conn(db, org_id, platform="meta", last_error="dead token") -> str:
    """Insert a PlatformConnection with a stamped last_error, return its id."""
    conn_id = uuid.uuid4()
    # platform_connections.platform_id is an FK to platforms; conftest only
    # seeds 'meta'. Ensure the platform row exists for any platform we test.
    db.execute(
        text(
            "INSERT INTO platforms (id, name) VALUES (:id, :id) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": platform},
    )
    db.execute(
        text(
            "INSERT INTO platform_connections "
            "(id, organization_id, platform_id, access_token, token_type, "
            " is_active, last_error, last_error_at) "
            "VALUES (:id, :org, :plat, 'tok', 'system_user', true, :err, now())"
        ),
        {"id": conn_id, "org": uuid.UUID(org_id), "plat": platform, "err": last_error},
    )
    db.flush()
    return str(conn_id)


def _open_token_alert(db, org_id, conn_id, notif_type="token_expired"):
    return notif_svc.create_notification(
        db, org_id=org_id, type=notif_type, severity="error",
        title="t", body="b", dedup_key=notif_svc.token_dedup_key(notif_type, conn_id),
    )


def test_resolve_connection_token_alerts_resolves_all_classes(db):
    """Each of token_expired/token_expiring/refresh_failed for the connection is
    marked resolved; an unrelated notification is left untouched."""
    org_id = make_org(db)
    conn_id = _make_conn(db, org_id)
    db.flush()

    expired = _open_token_alert(db, org_id, conn_id, "token_expired")
    expiring = _open_token_alert(db, org_id, conn_id, "token_expiring")
    failed = _open_token_alert(db, org_id, conn_id, "refresh_failed")
    unrelated = notif_svc.create_notification(
        db, org_id=org_id, type="sync_complete", severity="info",
        title="t", body="b", dedup_key="sync_complete:whatever",
    )

    n = notif_svc.resolve_connection_token_alerts(
        db, org_id=org_id, connection_id=conn_id
    )
    assert n == 3
    for row in (expired, expiring, failed):
        db.refresh(row)
        assert row.status == "resolved"
        assert row.resolved_at is not None
    db.refresh(unrelated)
    assert unrelated.status == "unread"  # untouched


def test_resolve_platform_token_alerts_across_multiple_connections(db):
    """Two meta connections in one org, each with an open token_expired alert +
    a stamped last_error → both alerts resolved and both last_errors cleared."""
    org_id = make_org(db)
    conn_a = _make_conn(db, org_id, platform="meta")
    conn_b = _make_conn(db, org_id, platform="meta")
    db.flush()

    alert_a = _open_token_alert(db, org_id, conn_a)
    alert_b = _open_token_alert(db, org_id, conn_b)

    n = notif_svc.resolve_platform_token_alerts(
        db, org_id=org_id, platform="meta"
    )
    assert n == 2

    db.refresh(alert_a)
    db.refresh(alert_b)
    assert alert_a.status == "resolved"
    assert alert_b.status == "resolved"

    for cid in (conn_a, conn_b):
        conn = db.get(PlatformConnection, uuid.UUID(cid))
        assert conn.last_error is None
        assert conn.last_error_at is None


def test_resolve_platform_token_alerts_tenant_and_platform_isolation(db):
    """Clearing meta alerts for org A must not touch org B's meta alert nor
    org A's tiktok alert (tenant + platform isolation)."""
    org_a = make_org(db, name="A")
    org_b = make_org(db, name="B")
    conn_a_meta = _make_conn(db, org_a, platform="meta")
    conn_a_tiktok = _make_conn(db, org_a, platform="tiktok")
    conn_b_meta = _make_conn(db, org_b, platform="meta")
    db.flush()

    a_meta = _open_token_alert(db, org_a, conn_a_meta)
    a_tiktok = _open_token_alert(db, org_a, conn_a_tiktok)
    b_meta = _open_token_alert(db, org_b, conn_b_meta)

    n = notif_svc.resolve_platform_token_alerts(
        db, org_id=org_a, platform="meta"
    )
    assert n == 1  # only org A's meta alert

    db.refresh(a_meta)
    db.refresh(a_tiktok)
    db.refresh(b_meta)
    assert a_meta.status == "resolved"
    assert a_tiktok.status == "unread"   # different platform, untouched
    assert b_meta.status == "unread"     # different org, untouched

    # last_error cleared only on the matched (org A meta) connection.
    assert db.get(PlatformConnection, uuid.UUID(conn_a_meta)).last_error is None
    assert db.get(PlatformConnection, uuid.UUID(conn_a_tiktok)).last_error is not None
    assert db.get(PlatformConnection, uuid.UUID(conn_b_meta)).last_error is not None


def test_resolve_platform_token_alerts_no_open_alert_is_noop(db):
    """Silent when everything is fine (P-2): reconnecting with no prior alert
    resolves nothing and does not error."""
    org_id = make_org(db)
    _make_conn(db, org_id, platform="meta", last_error=None)
    db.flush()
    assert notif_svc.resolve_platform_token_alerts(
        db, org_id=org_id, platform="meta"
    ) == 0


def test_token_dedup_key_is_stable_and_exported():
    """workers/token_alerts.py imports this — the format is load-bearing."""
    assert notif_svc.token_dedup_key("token_expired", "abc") == "token_expired:abc"
    assert notif_svc.TOKEN_ALERT_TYPES == (
        "token_expired", "token_expiring", "refresh_failed"
    )
