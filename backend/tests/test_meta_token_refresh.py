"""Meta token auto-refresh + token-expiry alerting (workers side).

Covers the plan's §Tests for the Meta refresh task:
- success exchanges the token, resets `token_expires_at`, clears health, and
  resolves any open alert (P-2 auto-clear).
- failure sets `last_error`/`last_error_at`, creates a `token_expired`
  notification, does NOT deactivate the Meta connection (unlike TikTok), and
  does not crash the task (P-8 durable trace).
- email is gated: sent once on a newly-created notification, not re-sent when an
  unresolved notification already exists.

The task normally opens its own `SessionLocal` via `get_worker_db()`. Here we
monkeypatch that to yield the isolated test-schema session (commit → flush) so
the task runs against the same rows the assertions read. The Meta HTTP exchange
and the email transport are both mocked — no network.
"""
import contextlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.models.notifications import Notification
from app.models.platform import PlatformConnection
from app.services.auth import encrypt_token, decrypt_token
from tests.conftest import make_org


@pytest.fixture
def worker_db(db, monkeypatch):
    """Point the task's get_worker_db at the isolated test session.

    The task calls get_worker_db() multiple times and relies on each `with`
    block committing; here we flush instead so everything stays inside the
    test's rolled-back transaction."""

    @contextlib.contextmanager
    def _fake_worker_db():
        try:
            yield db
            db.flush()
        except Exception:
            raise

    import workers.db_helpers as dbh
    monkeypatch.setattr(dbh, "get_worker_db", _fake_worker_db)
    # meta_token_refresh imports get_worker_db lazily inside the task body, so
    # patching the module attribute is enough.
    return db


def _make_meta_connection(db, org_id, *, expires_in_days=3, token="live-token") -> str:
    conn_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO platform_connections "
            "(id, organization_id, platform_id, access_token, token_type, "
            " is_active, token_expires_at) "
            "VALUES (:id, :org, 'meta', :tok, 'system_user', true, :exp)"
        ),
        {
            "id": conn_id,
            "org": uuid.UUID(org_id),
            "tok": encrypt_token(token),
            "exp": datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        },
    )
    db.flush()
    return str(conn_id)


def _make_owner(db, org_id, email="owner@x.co") -> None:
    uid = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, name, email_verified) "
            "VALUES (:id, :email, 'x', 'Owner', true)"
        ),
        {"id": uid, "email": email},
    )
    db.execute(
        text(
            "INSERT INTO organization_memberships (id, organization_id, user_id, role) "
            "VALUES (:id, :org, :uid, 'owner')"
        ),
        {"id": uuid.uuid4(), "org": uuid.UUID(org_id), "uid": uid},
    )
    db.flush()


def _run_refresh(monkeypatch, *, exchange_side_effect):
    """Patch MetaClient.exchange_long_lived_token + config, then run the task."""
    import workers.meta_client as mc
    from app.config import settings

    monkeypatch.setattr(settings, "META_APP_ID", "app-123", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "secret-xyz", raising=False)
    monkeypatch.setattr(
        mc.MetaClient, "exchange_long_lived_token",
        lambda self, app_id, app_secret, token: exchange_side_effect(token),
    )

    from workers.tasks.meta_token_refresh import refresh_meta_tokens
    # bind=True → call the underlying function with a dummy `self`.
    refresh_meta_tokens.run()


# ── success ──────────────────────────────────────────────────────────────────

def test_success_updates_token_and_expiry_and_resolves(worker_db, monkeypatch):
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id, token="old-token")

    # Pre-existing open alert from a prior failure — success must resolve it.
    db.execute(
        text(
            "INSERT INTO notifications "
            "(id, organization_id, type, severity, title, body, dedup_key, status) "
            "VALUES (:id, :org, 'token_expired', 'error', 't', 'b', :dk, 'unread')"
        ),
        {
            "id": uuid.uuid4(), "org": uuid.UUID(org_id),
            "dk": f"token_expired:{conn_id}",
        },
    )
    db.flush()

    _run_refresh(
        monkeypatch,
        exchange_side_effect=lambda token: {
            "access_token": "fresh-token",
            "expires_in": 5184000,  # ~60d
        },
    )

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    assert decrypt_token(conn.access_token) == "fresh-token"
    assert conn.is_active is True
    assert conn.last_error is None and conn.last_error_at is None
    # ~60d out, comfortably beyond the 7-day refresh cutoff.
    assert conn.token_expires_at > datetime.now(timezone.utc) + timedelta(days=50)

    notif = db.execute(
        select(Notification).where(
            Notification.dedup_key == f"token_expired:{conn_id}"
        )
    ).scalar_one()
    assert notif.status == "resolved"
    assert notif.resolved_at is not None


# ── failure ──────────────────────────────────────────────────────────────────

def test_failure_sets_last_error_creates_notif_and_keeps_active(worker_db, monkeypatch):
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id, token="dead-token")

    emails: list[str] = []
    import app.services.email as email_mod
    monkeypatch.setattr(
        email_mod, "_send", lambda to, subj, text_body, html_body: emails.append(to)
    )
    monkeypatch.setattr(email_mod, "_email_configured", lambda: True)
    _make_owner(db, org_id, email="owner@x.co")

    def _boom(token):
        from workers.meta_client import MetaAPIError
        raise MetaAPIError(code=190, subcode=460, message="OAuthException: token expired")

    # Token-shaped failure → handled as a token failure, must not raise.
    _run_refresh(monkeypatch, exchange_side_effect=_boom)

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    # Meta: connection stays active (recovers on re-paste) — unlike TikTok.
    assert conn.is_active is True
    assert conn.last_error is not None
    assert conn.last_error_at is not None
    # Token unchanged (exchange failed).
    assert decrypt_token(conn.access_token) == "dead-token"

    notif = db.execute(
        select(Notification).where(
            Notification.dedup_key == f"token_expired:{conn_id}"
        )
    ).scalar_one()
    assert notif.type == "token_expired"
    assert notif.severity == "error"
    assert notif.deep_link == "/settings/connections"
    assert notif.status == "unread"

    # Email sent once to the owner on the newly-created notification.
    assert emails == ["owner@x.co"]


def test_email_not_resent_when_notification_already_open(worker_db, monkeypatch):
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id, token="dead-token")
    _make_owner(db, org_id, email="owner@x.co")

    # Pre-existing unresolved alert for this connection → email must be gated off.
    db.execute(
        text(
            "INSERT INTO notifications "
            "(id, organization_id, type, severity, title, body, dedup_key, status) "
            "VALUES (:id, :org, 'token_expired', 'error', 't', 'b', :dk, 'unread')"
        ),
        {
            "id": uuid.uuid4(), "org": uuid.UUID(org_id),
            "dk": f"token_expired:{conn_id}",
        },
    )
    db.flush()

    emails: list[str] = []
    import app.services.email as email_mod
    monkeypatch.setattr(
        email_mod, "_send", lambda to, subj, text_body, html_body: emails.append(to)
    )
    monkeypatch.setattr(email_mod, "_email_configured", lambda: True)

    def _boom(token):
        from workers.meta_client import MetaAPIError
        raise MetaAPIError(code=190, subcode=460, message="still dead")

    _run_refresh(monkeypatch, exchange_side_effect=_boom)

    # No duplicate notification (DB dedup), and no re-sent email.
    count = db.execute(
        text(
            "SELECT count(*) FROM notifications WHERE dedup_key = :dk"
        ),
        {"dk": f"token_expired:{conn_id}"},
    ).scalar_one()
    assert count == 1
    assert emails == []


# ── falsy expires_in → never-expires (Finding 4) ──────────────────────────────

def test_success_no_expires_in_nulls_expiry_and_not_reselected(worker_db, monkeypatch):
    """A successful exchange that omits expires_in must NULL token_expires_at so
    the connection isn't re-selected (and re-exchanged) on the next run."""
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id, token="old-token")

    calls: list[str] = []

    def _exchange(token):
        calls.append(token)
        return {"access_token": "fresh-token"}  # no expires_in

    _run_refresh(monkeypatch, exchange_side_effect=_exchange)

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    assert decrypt_token(conn.access_token) == "fresh-token"
    # Falsy expires_in → treated as non-expiring.
    assert conn.token_expires_at is None
    assert conn.last_error is None
    assert len(calls) == 1

    # Second run: token_expires_at IS NULL → the refresh query must skip it, so
    # the exchange is NOT called again (no unbounded nightly re-exchange).
    _run_refresh(monkeypatch, exchange_side_effect=_exchange)
    assert len(calls) == 1


# ── infra error must NOT be mislabeled as a token failure (Finding 3) ──────────

def test_infra_error_does_not_stamp_last_error_or_notify(worker_db, monkeypatch):
    """A non-Meta/non-exchange exception (infra/config) must propagate via retry
    and NOT create a token_expired notification or stamp last_error (P-2)."""
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id, token="live-token")
    _make_owner(db, org_id, email="owner@x.co")

    emails: list[str] = []
    import app.services.email as email_mod
    monkeypatch.setattr(
        email_mod, "_send", lambda to, subj, text_body, html_body: emails.append(to)
    )
    monkeypatch.setattr(email_mod, "_email_configured", lambda: True)

    def _infra_boom(token):
        raise ConnectionError("database is down")

    # Unexpected error → escalates to Celery retry (raises Retry when a request
    # context exists, otherwise re-raises the original) — either way it does NOT
    # get swallowed as a token failure.
    with pytest.raises(Exception):
        _run_refresh(monkeypatch, exchange_side_effect=_infra_boom)

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    # Not a token problem: no warning lit, no email.
    assert conn.last_error is None
    assert conn.last_error_at is None
    assert emails == []

    count = db.execute(
        text("SELECT count(*) FROM notifications WHERE dedup_key = :dk"),
        {"dk": f"token_expired:{conn_id}"},
    ).scalar_one()
    assert count == 0


def test_no_appid_secret_is_a_noop(worker_db, monkeypatch):
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id, token="live")

    from app.config import settings
    monkeypatch.setattr(settings, "META_APP_ID", "", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "", raising=False)

    from workers.tasks.meta_token_refresh import refresh_meta_tokens
    refresh_meta_tokens.run()  # returns early, does nothing

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    assert decrypt_token(conn.access_token) == "live"
    assert conn.last_error is None
