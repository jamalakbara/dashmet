"""Unit tests for the Overview-page campaign filter resolver.

Covers `_resolve_campaign_ids` — the piece that decides whether the campaign
filter is active and builds the lookup query. The end-to-end SQL predicate
(`entity_id = ANY(CAST(:campaign_ids AS uuid[]))`) is Postgres-specific and
needs the DB test harness, which is not built yet (PRD §11) — verified manually.
"""
import uuid

from app.services.insights import _resolve_campaign_ids

ACCOUNT_ID = str(uuid.uuid4())


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Captures the SQL text + params passed to execute, returns canned rows."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return _FakeResult(self.rows)


def test_no_filter_returns_none_without_querying():
    db = _FakeSession()
    assert _resolve_campaign_ids(db, ACCOUNT_ID) is None
    # No filter active → must not touch the DB (predicate stays a no-op).
    assert db.calls == []


def test_empty_strings_are_treated_as_no_filter():
    db = _FakeSession()
    assert _resolve_campaign_ids(db, ACCOUNT_ID, status="", search="") is None
    assert db.calls == []


def test_status_only_builds_status_clause():
    db = _FakeSession(rows=[("c1",), ("c2",)])
    out = _resolve_campaign_ids(db, ACCOUNT_ID, status="active")
    sql, params = db.calls[0]
    assert "status = :status" in sql
    assert "name ILIKE" not in sql
    assert params["status"] == "active"
    assert params["account_id"] == uuid.UUID(ACCOUNT_ID)
    assert out == ["c1", "c2"]


def test_search_only_builds_ilike_clause():
    db = _FakeSession(rows=[("c9",)])
    out = _resolve_campaign_ids(db, ACCOUNT_ID, search="promo")
    sql, params = db.calls[0]
    assert "name ILIKE" in sql
    assert "status = :status" not in sql
    assert params["search"] == "promo"
    assert out == ["c9"]


def test_status_and_search_combine():
    db = _FakeSession(rows=[])
    out = _resolve_campaign_ids(db, ACCOUNT_ID, status="paused", search="sale")
    sql, params = db.calls[0]
    assert "status = :status" in sql
    assert "name ILIKE" in sql
    assert params["status"] == "paused"
    assert params["search"] == "sale"
    # Filter active but nothing matched → [] so downstream yields zero rows,
    # rather than None which would silently ignore the filter.
    assert out == []
