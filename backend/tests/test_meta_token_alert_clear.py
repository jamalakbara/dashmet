"""Sync-success clears an open token alert (workers side, recovery path P-2).

Companion to `test_meta_token_alerts.py` (which covers the *create*-on-auth-failure
path). Here the connection was previously in a failed state — an open
`token_expired` notification + `last_error` stamped — and a subsequent *successful*
sync must auto-resolve that notification and wipe `last_error` so the badge/banner
disappears without the user doing anything (P-2: warning clears when fine).

Driven through the Meta account-import task (`sync_accounts_for_connection`) with
`MetaClient.paginate` mocked to return an empty account list — a clean success
that exercises the `clear_connection_token_failure` call at the completion site.

The guard: a healthy connection (`last_error is None`) must NOT trigger a resolve —
the helper self-guards to avoid a pointless write every cycle.

`get_worker_db()` is monkeypatched to the isolated test session (flush, not commit)
so both the task body and the helper's own short txn land in the rolled-back
transaction. Email is disabled → dev no-op.
"""
import contextlib
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.models.notifications import Notification
from app.models.platform import PlatformConnection
from app.services.auth import encrypt_token
from app.services.notifications import token_dedup_key
from tests.conftest import make_org


@pytest.fixture
def worker_db(db, monkeypatch):
    """Point every task's get_worker_db at the isolated test session (flush, not
    commit). The clear helper opens its OWN get_worker_db txn — patching here
    means that re-fetch + resolve lands in the same session too."""

    @contextlib.contextmanager
    def _fake_worker_db():
        yield db
        db.flush()

    import workers.db_helpers as dbh
    monkeypatch.setattr(dbh, "get_worker_db", _fake_worker_db)
    return db


def _make_meta_connection(db, org_id, *, last_error) -> str:
    conn_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO platform_connections "
            "(id, organization_id, platform_id, access_token, token_type, "
            " is_active, last_error, last_error_at) "
            "VALUES (:id, :org, 'meta', :tok, 'system_user', true, :err, :err_at)"
        ),
        {
            "id": conn_id,
            "org": uuid.UUID(org_id),
            "tok": encrypt_token("live-token"),
            "err": last_error,
            "err_at": datetime.now(timezone.utc) if last_error else None,
        },
    )
    db.flush()
    return str(conn_id)


def _open_token_notification(db, org_id, conn_id) -> uuid.UUID:
    notif_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO notifications "
            "(id, organization_id, type, severity, title, body, dedup_key, status) "
            "VALUES (:id, :org, 'token_expired', 'error', 't', 'b', :dk, 'unread')"
        ),
        {
            "id": notif_id,
            "org": uuid.UUID(org_id),
            "dk": token_dedup_key("token_expired", conn_id),
        },
    )
    db.flush()
    return notif_id


def _disable_email(monkeypatch):
    import app.services.email as email_mod
    monkeypatch.setattr(email_mod, "_email_configured", lambda: False)


def _mock_clean_import(monkeypatch):
    """MetaClient.paginate returns no accounts → a clean, successful import."""
    import workers.meta_client as mc
    monkeypatch.setattr(mc.MetaClient, "paginate", lambda self, *a, **k: [])


def test_successful_sync_resolves_open_token_alert(worker_db, monkeypatch):
    """Connection had last_error + an open token_expired notification. A clean
    account import resolves the notification and clears last_error (P-2)."""
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id, last_error="Session has expired")
    notif_id = _open_token_notification(db, org_id, conn_id)
    _disable_email(monkeypatch)
    _mock_clean_import(monkeypatch)

    from workers.tasks.structure import sync_accounts_for_connection

    # Don't fan out to real downstream tasks — stub the eager dispatch.
    import workers.tasks.structure as struct_mod
    monkeypatch.setattr(struct_mod.sync_structure_all, "delay", lambda *a, **k: None)
    import workers.dispatch as dispatch_mod
    monkeypatch.setattr(dispatch_mod, "stagger_dispatch", lambda *a, **k: 0)

    sync_accounts_for_connection.run(conn_id, org_id)

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    assert conn.last_error is None
    assert conn.last_error_at is None

    notif = db.get(Notification, notif_id)
    assert notif.status == "resolved"
    assert notif.resolved_at is not None


def test_successful_sync_on_healthy_connection_is_noop(worker_db, monkeypatch):
    """Connection was already healthy (last_error is None). A clean sync must NOT
    touch the notification — the helper self-guards to skip a pointless resolve."""
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id, last_error=None)
    # A stray open notification with no last_error should be left ALONE — the
    # guard is `last_error is not None`, so a healthy connection never resolves.
    notif_id = _open_token_notification(db, org_id, conn_id)
    _disable_email(monkeypatch)
    _mock_clean_import(monkeypatch)

    from workers.tasks.structure import sync_accounts_for_connection

    import workers.tasks.structure as struct_mod
    monkeypatch.setattr(struct_mod.sync_structure_all, "delay", lambda *a, **k: None)
    import workers.dispatch as dispatch_mod
    monkeypatch.setattr(dispatch_mod, "stagger_dispatch", lambda *a, **k: 0)

    sync_accounts_for_connection.run(conn_id, org_id)

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    assert conn.last_error is None

    # Untouched — still unread, not resolved (no-op path).
    notif = db.get(Notification, notif_id)
    assert notif.status == "unread"
    assert notif.resolved_at is None


def test_clear_helper_swallows_its_own_errors(monkeypatch):
    """Clearing must never fail a sync that otherwise succeeded — a broken
    get_worker_db inside the helper is logged and swallowed, not raised."""
    import workers.token_alerts as ta

    @contextlib.contextmanager
    def _boom_db():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr("workers.db_helpers.get_worker_db", _boom_db)
    # Must not raise.
    ta.clear_connection_token_failure(str(uuid.uuid4()))
