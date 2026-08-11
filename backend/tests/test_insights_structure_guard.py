"""Insights livelock guard (Meta).

Regression for the prod livelock where `sync_insights_for_account` fetched
campaign + per-campaign adset/ad insights and then raised on an empty
`adgroup_map`, burning the shared Meta *app* quota that `structure` needs to
complete. That starved structure (its `apply_backoff` skipped), so `campaigns`
stayed empty and insights failed forever.

Guard: if there are no campaigns for the account, insights must return BEFORE
constructing MetaClient / making any API call.
- structure never completed  -> trigger structure, defer, no Meta call.
- structure completed, 0 campaigns -> return cleanly, do NOT re-trigger structure.
- campaigns present -> guard is a no-op (task proceeds past it).
"""
import contextlib
import uuid

import pytest
from sqlalchemy import text

from tests.conftest import make_campaign


@pytest.fixture
def worker_db(db, monkeypatch):
    """Point the task's get_worker_db at the isolated test session (flush, not commit)."""

    @contextlib.contextmanager
    def _fake_worker_db():
        yield db
        db.flush()

    import workers.db_helpers as dbh
    monkeypatch.setattr(dbh, "get_worker_db", _fake_worker_db)
    return db


@pytest.fixture
def no_meta(monkeypatch):
    """Fail loudly if the task constructs a MetaClient — the whole point of the
    guard is that no API call happens when campaigns are missing."""
    import workers.meta_client as mc

    def _boom(*_a, **_k):
        raise AssertionError("MetaClient must not be constructed when campaigns are empty")

    monkeypatch.setattr(mc, "MetaClient", _boom)


@pytest.fixture
def spy_structure(monkeypatch):
    """Record calls to sync_structure_for_account.delay without hitting a broker."""
    import workers.tasks.structure as st
    calls = []
    monkeypatch.setattr(st.sync_structure_for_account, "delay", lambda *a, **k: calls.append(a))
    return calls


def _insights_job_count(db, account_id: str) -> int:
    row = db.execute(
        text(
            "SELECT count(*) FROM sync_jobs "
            "WHERE account_id = :a AND job_type = 'insights_daily'"
        ),
        {"a": uuid.UUID(account_id)},
    ).scalar()
    return int(row)


def _complete_structure_job(db, account_id: str):
    db.execute(
        text(
            "INSERT INTO sync_jobs (id, account_id, platform_id, job_type, status, completed_at) "
            "VALUES (:id, :a, 'meta', 'structure', 'completed', now())"
        ),
        {"id": uuid.uuid4(), "a": uuid.UUID(account_id)},
    )
    db.flush()


def test_no_campaigns_defers_and_triggers_structure(
    worker_db, no_meta, spy_structure, seeded_account
):
    """No campaigns + structure never completed: no Meta call, no insights job
    row created, and structure is triggered to run first."""
    from workers.tasks.insights import sync_insights_for_account

    account_id = seeded_account["account_id"]

    # force=True bypasses the freshness check so we exercise the guard directly.
    result = sync_insights_for_account(account_id, force=True)

    assert result is None
    assert spy_structure == [(account_id,)], "structure should be triggered once"
    assert _insights_job_count(worker_db, account_id) == 0, "no insights job before Meta call"


def test_no_campaigns_but_structure_done_returns_clean(
    worker_db, no_meta, spy_structure, seeded_account
):
    """Structure completed and the account genuinely has 0 campaigns: return
    cleanly — no Meta call, and do NOT re-trigger structure (nothing to sync)."""
    from workers.tasks.insights import sync_insights_for_account

    account_id = seeded_account["account_id"]
    _complete_structure_job(worker_db, account_id)

    result = sync_insights_for_account(account_id, force=True)

    assert result is None
    assert spy_structure == [], "structure must not be re-triggered when it already completed"
    assert _insights_job_count(worker_db, account_id) == 0


def test_campaigns_present_passes_guard(
    worker_db, monkeypatch, spy_structure, seeded_account
):
    """With a campaign present the guard is a no-op: the task moves PAST it into
    Phase 2, where it commits a 'running' insights_daily job before the first API
    call. We stub the token/lock/Redis deps and make MetaClient raise so no
    network happens; reaching the job-creation proves the guard let it through."""
    import workers.meta_client as mc
    import workers.rate_limit as rl
    import app.services.auth as auth

    account_id = seeded_account["account_id"]
    make_campaign(worker_db, account_id)
    worker_db.flush()

    monkeypatch.setattr(auth, "decrypt_token", lambda *_a, **_k: "plain")
    monkeypatch.setattr(rl, "connection_paused_remaining", lambda *_a, **_k: 0)
    monkeypatch.setattr(rl, "acquire_lock", lambda *_a, **_k: "lock-token")
    monkeypatch.setattr(rl, "release_lock", lambda *_a, **_k: None)

    def _boom(*_a, **_k):
        raise RuntimeError("stop before network")

    monkeypatch.setattr(mc, "MetaClient", _boom)

    from workers.tasks.insights import sync_insights_for_account

    # Downstream the task catches the error, finalizes the job 'failed', and calls
    # self.retry (which raises Retry in eager mode). We don't care which exception
    # surfaces — only that the guard did NOT short-circuit.
    with pytest.raises(Exception):
        sync_insights_for_account(account_id, force=True)

    assert spy_structure == [], "guard should not trigger structure when campaigns exist"
    assert _insights_job_count(worker_db, account_id) >= 1, "guard passed → Phase-2 job created"
