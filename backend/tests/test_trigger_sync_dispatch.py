"""Platform-aware /sync/trigger dispatch (Bug A + Bug B).

Bug A: job_types is now optional — a bare {account_id} POST must NOT 400.
Bug B: dispatch must branch on account.platform_id so a TikTok/Google account
runs the TikTok/Google tasks, not the Meta ones — and must NEVER create a
`pending` SyncJob row for a (platform, job_type) pair with no producer (P-8).
"""
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from app.exceptions import ForbiddenError, NotFoundError
from app.models.metrics import SyncJob
from app.services import sync as sync_svc
from tests.conftest import make_org, make_connection, make_account


# ─── platform-parametric seeding ────────────────────────────────────────────

def _ensure_platform(db, platform_id: str) -> None:
    db.execute(
        text(
            "INSERT INTO platforms (id, name) VALUES (:id, :name) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": platform_id, "name": platform_id},
    )


def _make_account_on_platform(db, platform_id: str) -> tuple[str, str]:
    """Returns (org_id, account_id) for an account on the given platform."""
    _ensure_platform(db, platform_id)
    org_id = make_org(db, name=f"Org-{platform_id}")
    conn_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO platform_connections "
            "(id, organization_id, platform_id, access_token, token_type, is_active) "
            "VALUES (:id, :org, :plat, 'tok', 'system_user', true)"
        ),
        {"id": conn_id, "org": uuid.UUID(org_id), "plat": platform_id},
    )
    acct_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO accounts "
            "(id, organization_id, platform_connection_id, platform_id, "
            " external_id, name, currency, timezone, account_status) "
            "VALUES (:id, :org, :conn, :plat, :ext, :name, 'USD', 'UTC', 'active')"
        ),
        {
            "id": acct_id, "org": uuid.UUID(org_id), "conn": conn_id,
            "plat": platform_id, "ext": f"ext_{acct_id.hex[:8]}",
            "name": f"Acct-{platform_id}",
        },
    )
    db.flush()
    return org_id, str(acct_id)


@pytest.fixture
def patched_dispatch(monkeypatch):
    """Replace every dispatch fn in DISPATCH_TABLE with a MagicMock so no real
    Celery import/.delay happens. Returns {(platform, job_type): mock}."""
    mocks: dict[tuple[str, str], MagicMock] = {}
    for platform, jobs in sync_svc.DISPATCH_TABLE.items():
        new_jobs = {}
        for jt in jobs:
            m = MagicMock(name=f"{platform}:{jt}")
            mocks[(platform, jt)] = m
            new_jobs[jt] = m
        monkeypatch.setitem(sync_svc.DISPATCH_TABLE, platform, new_jobs)
    return mocks


def _sync_jobs_for(db, account_id: str) -> list[SyncJob]:
    return (
        db.query(SyncJob)
        .filter(SyncJob.account_id == uuid.UUID(account_id))
        .all()
    )


# ─── Bug B: TikTok dispatches TikTok tasks, not Meta ─────────────────────────

def test_tiktok_trigger_dispatches_tiktok_tasks(db, patched_dispatch):
    org_id, account_id = _make_account_on_platform(db, "tiktok")

    job_ids = sync_svc.trigger_sync(
        db, account_id, org_id, ["structure", "insights_daily"]
    )

    # TikTok producers called with the account id...
    patched_dispatch[("tiktok", "structure")].assert_called_once_with(account_id)
    patched_dispatch[("tiktok", "insights_daily")].assert_called_once_with(account_id)
    # ...and the Meta ones NOT called.
    patched_dispatch[("meta", "structure")].assert_not_called()
    patched_dispatch[("meta", "insights_daily")].assert_not_called()

    # One SyncJob row per dispatched job_type, all with the tiktok platform.
    rows = _sync_jobs_for(db, account_id)
    assert {r.job_type for r in rows} == {"structure", "insights_daily"}
    assert all(r.platform_id == "tiktok" for r in rows)
    assert all(r.status == "pending" for r in rows)
    assert len(job_ids) == 2


def test_google_trigger_dispatches_google_tasks(db, patched_dispatch):
    org_id, account_id = _make_account_on_platform(db, "google_ads")

    sync_svc.trigger_sync(db, account_id, org_id, ["structure", "breakdown"])

    patched_dispatch[("google_ads", "structure")].assert_called_once_with(account_id)
    patched_dispatch[("google_ads", "breakdown")].assert_called_once_with(account_id)
    patched_dispatch[("meta", "structure")].assert_not_called()

    rows = _sync_jobs_for(db, account_id)
    assert {r.job_type for r in rows} == {"structure", "breakdown"}
    assert all(r.platform_id == "google_ads" for r in rows)


# ─── Bug A: job_types omitted → platform default, no 400 ─────────────────────

def test_trigger_with_none_job_types_uses_tiktok_default(db, patched_dispatch):
    org_id, account_id = _make_account_on_platform(db, "tiktok")

    # This mirrors the frontend's bare {account_id} call — job_types omitted.
    job_ids = sync_svc.trigger_sync(db, account_id, org_id, None)

    expected = set(sync_svc.DEFAULT_JOB_TYPES["tiktok"])
    rows = _sync_jobs_for(db, account_id)
    assert {r.job_type for r in rows} == expected
    assert len(job_ids) == len(expected)
    for jt in expected:
        patched_dispatch[("tiktok", jt)].assert_called_once_with(account_id)


def test_trigger_with_none_job_types_uses_meta_default(db, patched_dispatch):
    org_id, account_id = _make_account_on_platform(db, "meta")

    sync_svc.trigger_sync(db, account_id, org_id, None)

    expected = set(sync_svc.DEFAULT_JOB_TYPES["meta"])
    rows = _sync_jobs_for(db, account_id)
    assert {r.job_type for r in rows} == expected


# ─── P-8: no pending row for a (platform, job_type) with no producer ─────────

def test_no_pending_row_without_producer(db, patched_dispatch):
    org_id, account_id = _make_account_on_platform(db, "tiktok")

    # insights_async has a Meta producer but NONE for tiktok — it must be
    # skipped entirely, not left as a stuck pending row.
    assert "insights_async" not in sync_svc.DISPATCH_TABLE["tiktok"]

    sync_svc.trigger_sync(
        db, account_id, org_id, ["structure", "insights_async"]
    )

    rows = _sync_jobs_for(db, account_id)
    job_types = {r.job_type for r in rows}
    assert "insights_async" not in job_types, "created a pending row with no producer (P-8)"
    assert job_types == {"structure"}


def test_default_job_types_all_have_producers():
    """Every default job_type must map to a producer for its platform (P-8)."""
    for platform, jts in sync_svc.DEFAULT_JOB_TYPES.items():
        table = sync_svc.DISPATCH_TABLE.get(platform, {})
        for jt in jts:
            assert jt in table, f"default {platform}/{jt} has no producer"
            assert jt in sync_svc.JOB_TTLS, f"default {platform}/{jt} not a tracked job_type"


# ─── Tenant isolation stays intact ───────────────────────────────────────────

def test_cross_org_account_is_forbidden(db, patched_dispatch):
    org_id, account_id = _make_account_on_platform(db, "tiktok")
    other_org = make_org(db, name="Attacker")
    db.flush()

    with pytest.raises(ForbiddenError):
        sync_svc.trigger_sync(db, account_id, other_org, None)

    # No jobs created, no dispatch fired.
    assert _sync_jobs_for(db, account_id) == []


def test_unknown_account_is_not_found(db, patched_dispatch):
    org_id = make_org(db, name="Org")
    db.flush()
    with pytest.raises(NotFoundError):
        sync_svc.trigger_sync(db, str(uuid.uuid4()), org_id, None)
