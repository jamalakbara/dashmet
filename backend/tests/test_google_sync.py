"""Unit tests for the Google Ads sync mapping logic (no network / SDK needed).

The mapping tests below need neither DB nor SDK. The account-import auth-alert
test at the bottom is DB-backed (isolated test session) and mocks GoogleClient +
email — no network.
"""
import contextlib
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from workers.tasks.google_insights import parse_google_report_row
from workers.tasks.google_structure import (
    GOOGLE_STATUS_MAP,
    GOOGLE_OBJECTIVE_MAP,
    _micros_to_units,
)
from workers.tasks.google_breakdowns import _aggregate, _AGE_MAP, _GENDER_MAP

ACC = uuid.uuid4()
ENT = uuid.uuid4()


def _actions_by_field(rows):
    return {(r["field_name"], r["action_type"]): r["value"] for r in rows}


def test_parse_core_scalars_micros_and_ctr():
    raw = {
        "campaign.id": "111",
        "segments.date": "2026-06-01",
        "metrics.impressions": "1000",
        "metrics.clicks": "50",
        "metrics.cost_micros": "5000000",      # 5.0 units
        "metrics.average_cpc": "100000",        # 0.1 units
        "metrics.average_cpm": "5000000",       # 5.0 units
        "metrics.ctr": 0.05,                    # → 5.0 (percent)
    }
    scalars, _ = parse_google_report_row("campaign", ENT, ACC, date(2026, 6, 1), raw)
    assert scalars["impressions"] == 1000
    assert scalars["clicks"] == 50
    assert scalars["spend"] == 5.0
    assert scalars["cpc"] == 0.1
    assert scalars["cpm"] == 5.0
    assert scalars["ctr"] == 5.0
    assert scalars["platform_id"] == "google_ads"


def test_parse_conversions_map_to_roas_join_fields():
    raw = {
        "metrics.conversions": 12,
        "metrics.conversions_value": 480.0,
    }
    _, actions = parse_google_report_row(
        "campaign", ENT, ACC, date(2026, 6, 1), raw,
        primary_conversion_action="purchase", roas_action_type="purchase",
    )
    by = _actions_by_field(actions)
    # conversions → field_name 'conversions'; value → field_name 'action_values'
    assert by[("conversions", "purchase")] == Decimal("12")
    assert by[("action_values", "purchase")] == Decimal("480.0")


def test_parse_video_views_and_quartile_counts():
    raw = {
        "metrics.impressions": "1000",
        "metrics.video_views": "400",
        "metrics.video_quartile_p25_rate": 0.5,    # → 500
        "metrics.video_quartile_p100_rate": 0.1,   # → 100
    }
    _, actions = parse_google_report_row("ad", ENT, ACC, date(2026, 6, 1), raw)
    by = _actions_by_field(actions)
    assert by[("video_play_actions", "video_view")] == Decimal("400")
    assert by[("video_p25_watched_actions", "video_view")] == Decimal("500")
    assert by[("video_p100_watched_actions", "video_view")] == Decimal("100")


def test_empty_metrics_emit_no_action_rows():
    scalars, actions = parse_google_report_row("campaign", ENT, ACC, date(2026, 6, 1), {})
    assert actions == []
    assert scalars["spend"] is None


def test_structure_mappers():
    assert GOOGLE_STATUS_MAP["ENABLED"] == "active"
    assert GOOGLE_STATUS_MAP["REMOVED"] == "deleted"
    assert GOOGLE_OBJECTIVE_MAP["SEARCH"] == "traffic"
    assert GOOGLE_OBJECTIVE_MAP["PERFORMANCE_MAX"] == "sales"
    assert _micros_to_units("5000000") == 5.0
    assert _micros_to_units(None) is None


def test_breakdown_aggregate_and_maps():
    rows = [
        {"segments.device": "MOBILE", "metrics.impressions": "100", "metrics.clicks": "10",
         "metrics.cost_micros": "1000000", "metrics.conversions": 2},
        {"segments.device": "MOBILE", "metrics.impressions": "50", "metrics.clicks": "5",
         "metrics.cost_micros": "500000", "metrics.conversions": 1},
        {"segments.device": "DESKTOP", "metrics.impressions": "10", "metrics.clicks": "1",
         "metrics.cost_micros": "100000", "metrics.conversions": 0},
    ]
    agg = _aggregate(rows, lambda r: r.get("segments.device"))
    assert agg["MOBILE"]["impressions"] == 150
    assert agg["MOBILE"]["spend"] == 1.5
    assert agg["MOBILE"]["conversions"] == 3
    assert agg["DESKTOP"]["clicks"] == 1
    assert _AGE_MAP["AGE_RANGE_25_34"] == "25-34"
    assert _GENDER_MAP["UNDETERMINED"] == "unknown"


# ── account-import auth alert (Finding 2) ─────────────────────────────────────


@pytest.fixture
def worker_db(db, monkeypatch):
    """Point the task's get_worker_db at the isolated test session (flush, not
    commit) so alert writes land in the same rolled-back transaction."""

    @contextlib.contextmanager
    def _fake_worker_db():
        yield db
        db.flush()

    import workers.db_helpers as dbh
    monkeypatch.setattr(dbh, "get_worker_db", _fake_worker_db)
    return db


def _make_google_connection(db, org_id) -> str:
    from app.services.auth import encrypt_token
    conn_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO platform_connections "
            "(id, organization_id, platform_id, access_token, refresh_token, "
            " token_type, is_active) "
            "VALUES (:id, :org, 'google_ads', :tok, :rtok, 'oauth', true)"
        ),
        {
            "id": conn_id,
            "org": uuid.UUID(org_id),
            "tok": encrypt_token("access"),
            "rtok": encrypt_token("refresh"),
        },
    )
    db.flush()
    return str(conn_id)


def test_account_import_auth_failure_alerts(worker_db, monkeypatch):
    """An auth GoogleAdsClientError during account import must leave a durable
    token trace (notification + last_error) — this is the first Google call to
    run against a connection, so a revoked grant surfaces here first."""
    from tests.conftest import make_org
    from app.models.platform import PlatformConnection
    from app.models.notifications import Notification

    db = worker_db
    org_id = make_org(db)
    db.flush()
    conn_id = _make_google_connection(db, org_id)

    # Email off → dev no-op (no transport), keeps the durable trace as the SoT.
    import app.services.email as email_mod
    monkeypatch.setattr(email_mod, "_email_configured", lambda: False)

    import workers.google_client as gc

    class _FakeClient:
        def __init__(self, refresh_token):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def list_accessible_customers(self):
            raise gc.GoogleAdsClientError("UNAUTHENTICATED: token revoked", is_auth=True)

        def list_customer_clients(self, login_cid):
            raise gc.GoogleAdsClientError("UNAUTHENTICATED: token revoked", is_auth=True)

    monkeypatch.setattr(gc, "GoogleClient", _FakeClient)
    # No MCC → forces the list_accessible_customers path.
    from app.config import settings
    monkeypatch.setattr(settings, "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "", raising=False)

    from workers.tasks.google_structure import sync_google_accounts_for_connection

    # The task re-raises via self.retry after alerting; we only care about the trace.
    with pytest.raises(Exception):
        sync_google_accounts_for_connection.run(conn_id, org_id)

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
