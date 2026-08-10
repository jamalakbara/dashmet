"""Meta/TikTok sync-path token-expiry alerting (workers side).

Regression coverage for the bug where a dead Meta/TikTok access token during a
normal *sync* task produced failed sync_jobs but ZERO notifications and empty
`last_error` — the alert funnel was only wired into Google sync + the
Meta/TikTok *refresh* tasks, never the Meta/TikTok *sync* tasks.

Two layers:
- Pure classifier tests for `MetaAPIError.is_auth` / `TikTokAPIError.is_auth`
  (no DB, no network) — these are the gate that decides "alert vs. retry".
- DB-backed account-import tests that mirror
  `test_google_sync.py::test_account_import_auth_failure_alerts`: an auth error
  leaves a durable trace (notification + last_error); a non-auth error does not
  cry wolf (P-2).

The task's `get_worker_db()` is monkeypatched to the isolated test session
(commit → flush) and email is disabled → dev no-op, so the DB notification is
the source of truth.
"""
import contextlib
import uuid

import pytest
from sqlalchemy import select, text

from app.models.notifications import Notification
from app.models.platform import PlatformConnection
from app.services.auth import encrypt_token
from tests.conftest import make_org


# ── classifier: MetaAPIError.is_auth ──────────────────────────────────────────

def test_meta_is_auth_true_for_expired_token_code_190():
    from workers.meta_client import MetaAPIError
    err = MetaAPIError(code=190, subcode=None, message="Session has expired")
    assert err.is_auth is True


def test_meta_is_auth_true_for_session_code_102():
    from workers.meta_client import MetaAPIError
    err = MetaAPIError(code=102, subcode=None, message="API session")
    assert err.is_auth is True


def test_meta_is_auth_true_for_oauth_subcode():
    from workers.meta_client import MetaAPIError
    # code carries a generic value but the subcode is an OAuth auth subcode.
    err = MetaAPIError(code=190, subcode=463, message="expired session")
    assert err.is_auth is True


def test_meta_is_auth_false_for_rate_limit_code_17():
    from workers.meta_client import MetaAPIError
    err = MetaAPIError(code=17, subcode=None, message="User request limit reached")
    assert err.is_auth is False


def test_meta_is_auth_false_for_generic_code_100():
    from workers.meta_client import MetaAPIError
    err = MetaAPIError(code=100, subcode=33, message="missing permission")
    assert err.is_auth is False


# ── classifier: TikTokAPIError.is_auth ────────────────────────────────────────

@pytest.mark.parametrize("code", [40100, 40101, 40200])
def test_tiktok_is_auth_true_for_token_codes(code):
    from workers.tiktok_client import TikTokAPIError
    assert TikTokAPIError(code=code, message="x").is_auth is True


@pytest.mark.parametrize("code", [40001, 40002, 40300, 50002])
def test_tiktok_is_auth_false_for_non_auth_codes(code):
    from workers.tiktok_client import TikTokAPIError
    assert TikTokAPIError(code=code, message="x").is_auth is False


# ── DB-backed fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def worker_db(db, monkeypatch):
    """Point every task's get_worker_db at the isolated test session (flush, not
    commit) so alert writes land in the same rolled-back transaction."""

    @contextlib.contextmanager
    def _fake_worker_db():
        yield db
        db.flush()

    import workers.db_helpers as dbh
    monkeypatch.setattr(dbh, "get_worker_db", _fake_worker_db)
    return db


def _make_meta_connection(db, org_id) -> str:
    conn_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO platform_connections "
            "(id, organization_id, platform_id, access_token, token_type, is_active) "
            "VALUES (:id, :org, 'meta', :tok, 'system_user', true)"
        ),
        {"id": conn_id, "org": uuid.UUID(org_id), "tok": encrypt_token("dead-token")},
    )
    db.flush()
    return str(conn_id)


def _make_tiktok_connection(db, org_id) -> str:
    conn_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO platform_connections "
            "(id, organization_id, platform_id, access_token, token_type, is_active) "
            "VALUES (:id, :org, 'tiktok', :tok, 'oauth', true)"
        ),
        {"id": conn_id, "org": uuid.UUID(org_id), "tok": encrypt_token("dead-token")},
    )
    db.flush()
    return str(conn_id)


def _disable_email(monkeypatch):
    import app.services.email as email_mod
    monkeypatch.setattr(email_mod, "_email_configured", lambda: False)


# ── Meta account-import: auth error alerts, non-auth error stays silent ───────

def test_meta_account_import_auth_failure_alerts(worker_db, monkeypatch):
    """A code-190 MetaAPIError during account import leaves a durable token
    trace (token_expired notification + last_error) — the sync path now funnels
    into the same alert as Google, not just the refresh task."""
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id)
    _disable_email(monkeypatch)

    import workers.meta_client as mc

    def _boom(self, *a, **k):
        raise mc.MetaAPIError(code=190, subcode=None, message="Session has expired")

    monkeypatch.setattr(mc.MetaClient, "paginate", _boom)

    from workers.tasks.structure import sync_accounts_for_connection

    with pytest.raises(Exception):
        sync_accounts_for_connection.run(conn_id, org_id)

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    assert conn.last_error is not None
    assert conn.last_error_at is not None

    notif = db.execute(
        select(Notification).where(
            Notification.dedup_key == f"token_expired:{conn_id}"
        )
    ).scalar_one()
    assert notif.type == "token_expired"
    assert notif.severity == "error"
    assert notif.deep_link == "/settings/connections"


def test_meta_account_import_non_auth_error_does_not_alert(worker_db, monkeypatch):
    """A non-auth MetaAPIError (e.g. rate-limit code 17) must NOT create a
    token_expired notification — don't cry wolf on transient failures (P-2)."""
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_meta_connection(db, org_id)
    _disable_email(monkeypatch)

    import workers.meta_client as mc

    def _boom(self, *a, **k):
        raise mc.MetaAPIError(code=17, subcode=None, message="request limit reached")

    monkeypatch.setattr(mc.MetaClient, "paginate", _boom)

    from workers.tasks.structure import sync_accounts_for_connection

    with pytest.raises(Exception):
        sync_accounts_for_connection.run(conn_id, org_id)

    notif = db.execute(
        select(Notification).where(
            Notification.dedup_key == f"token_expired:{conn_id}"
        )
    ).first()
    assert notif is None


# ── TikTok account-import: auth error alerts, non-auth stays silent ───────────

def test_tiktok_account_import_auth_failure_alerts(worker_db, monkeypatch):
    """A code-40101 (token expired) TikTokAPIError during account import leaves a
    durable token trace — TikTok sync now funnels into the alert path too."""
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_tiktok_connection(db, org_id)
    _disable_email(monkeypatch)

    import workers.tiktok_client as tc

    def _boom(self, ids):
        raise tc.TikTokAPIError(code=40101, message="Access token expired")

    monkeypatch.setattr(tc.TikTokClient, "get_advertiser_info", _boom)

    from workers.tasks.tiktok_structure import sync_tiktok_accounts_for_connection

    with pytest.raises(Exception):
        sync_tiktok_accounts_for_connection.run(conn_id, org_id, ["adv-1"])

    conn = db.get(PlatformConnection, uuid.UUID(conn_id))
    assert conn.last_error is not None
    assert conn.last_error_at is not None

    notif = db.execute(
        select(Notification).where(
            Notification.dedup_key == f"token_expired:{conn_id}"
        )
    ).scalar_one()
    assert notif.type == "token_expired"
    assert notif.severity == "error"


def test_tiktok_account_import_non_auth_error_does_not_alert(worker_db, monkeypatch):
    """A non-auth TikTokAPIError (e.g. rate-limit 40300) must NOT alert (P-2)."""
    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_tiktok_connection(db, org_id)
    _disable_email(monkeypatch)

    import workers.tiktok_client as tc

    def _boom(self, ids):
        raise tc.TikTokAPIError(code=40300, message="Rate limit exceeded")

    monkeypatch.setattr(tc.TikTokClient, "get_advertiser_info", _boom)

    from workers.tasks.tiktok_structure import sync_tiktok_accounts_for_connection

    with pytest.raises(Exception):
        sync_tiktok_accounts_for_connection.run(conn_id, org_id, ["adv-1"])

    notif = db.execute(
        select(Notification).where(
            Notification.dedup_key == f"token_expired:{conn_id}"
        )
    ).first()
    assert notif is None
