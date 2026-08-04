"""Endpoint tests for POST /insights/overview/summary (the AI diagnosis card).

The insights service is raw-Postgres-specific and the shared `db` fixture needs
a reachable Postgres (see conftest). Rather than gate these behind a live DB,
these tests call the endpoint FUNCTION directly and mock the seams the handler
sits between — the three shared read functions (`insights_svc.get_overview`,
`insights_svc.get_table`, `insights_svc.get_timeseries`) and the OpenAI call
(`ai_summary_svc.generate_overview_diagnosis`). That lets us pin the handler's
own logic — tenant-error passthrough, read→diagnose parity (P-6), and
AISummaryError→502 (P-4) — with zero DB and zero network.

Each test documents exactly which layer is mocked and why.

Run:
    cd backend && \
    $HOME/.pyenv/versions/3.12.13/bin/python -m pytest tests/test_overview_summary_endpoint.py -v
"""
import types
import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import insights as insights_ep
from app.exceptions import ForbiddenError
from app.services import ai_summary as ai_summary_svc


def _overview_payload():
    """Shaped like insights_svc.get_overview's return value."""
    return {
        "period": {"date_start": date(2026, 6, 1), "date_stop": date(2026, 6, 30),
                   "preset": "last_30d"},
        "summary": {"spend": 12345.67, "impressions": 2_500_000, "clicks": 48_000,
                    "ctr": 1.92, "cpm": 4.94, "conversions": 1_234, "roas": 3.75},
        "previous": {"spend": 11000.0},
        "vs_previous": {"spend": 12.3},
        "top_campaigns": [{"name": "Alpha", "spend": 5000.0, "ctr": 2.1,
                           "conversions": 600.0, "roas": 4.0}],
    }


def _campaigns_payload():
    """Shaped like insights_svc.get_table(level="campaign", compare_previous=True):
    a (rows, total) tuple — the handler unpacks `campaigns, _total`."""
    rows = [
        {"name": "Alpha", "status": "ACTIVE", "objective": "OUTCOME_SALES",
         "metrics": {"spend": 5000.0, "roas": 4.0, "conversions": 600.0, "ctr": 2.1},
         "metrics_previous": {"spend": 4800.0, "roas": 6.0, "conversions": 900.0, "ctr": 2.3}},
    ]
    return rows, len(rows)


def _timeseries_payload():
    """Shaped like insights_svc.get_timeseries(compare_previous=True)."""
    return {
        "series": [{"date": date(2026, 6, 1), "spend": 400.0, "conversions": 42}],
        "previous_series": [{"date": date(2026, 5, 1), "spend": 380.0, "conversions": 60}],
    }


def _card():
    """A valid structured diagnosis the mocked AI service returns."""
    return {
        "headline": "Conversions down on flat spend.",
        "driver": "Alpha (SALES) drove the drop.",
        "watch": "CTR softening.",
        "next_step": "Audit Alpha targeting.",
    }


def _account(currency="USD", tz="UTC"):
    return types.SimpleNamespace(currency=currency, timezone=tz, name="Acct")


def _owner(org_id="org-1"):
    return {"org_id": org_id, "sub": str(uuid.uuid4()), "role": "owner"}


def _stub_all_reads(monkeypatch, *, account, overview=None, campaigns=None, timeseries=None):
    """Stub the tenant guard + resolver + all three shared read functions so the
    handler runs DB-free. Returns the objects used, for identity assertions."""
    overview = overview if overview is not None else _overview_payload()
    campaigns = campaigns if campaigns is not None else _campaigns_payload()
    timeseries = timeseries if timeseries is not None else _timeseries_payload()

    monkeypatch.setattr(
        insights_ep.acc_svc, "assert_account_belongs_to_org",
        lambda db, account_id, org_id: account,
    )
    monkeypatch.setattr(
        insights_ep.insights_svc, "resolve_date_range",
        lambda preset, tz: (date(2026, 6, 1), date(2026, 6, 30)),
    )
    monkeypatch.setattr(
        insights_ep.insights_svc, "get_overview", lambda *a, **k: overview,
    )
    monkeypatch.setattr(
        insights_ep.insights_svc, "get_table", lambda *a, **k: campaigns,
    )
    monkeypatch.setattr(
        insights_ep.insights_svc, "get_timeseries", lambda *a, **k: timeseries,
    )
    return overview, campaigns, timeseries


# ─── 2a. Tenant isolation: cross-org account_id → 403 ────────────────────────


def test_summary_cross_org_returns_403(monkeypatch):
    """A caller whose org doesn't own account_id gets 403.

    MOCKED: `acc_svc.assert_account_belongs_to_org` — the real tenant guard that
    _resolve_dates calls. We make it raise ForbiddenError exactly as the real
    function does for a cross-org id; the handler must translate that to
    HTTPException(403). The guard runs first (inside _resolve_dates), before any
    read or AI call.

    generate_overview_diagnosis must NEVER be reached for a forbidden account
    (no tokens spent on an unauthorized read) — we assert that too."""
    def _forbidden(db, account_id, org_id):
        raise ForbiddenError("Account does not belong to your organization")

    monkeypatch.setattr(insights_ep.acc_svc, "assert_account_belongs_to_org", _forbidden)

    called = {"diagnose": False}

    def _diagnose(*a, **k):
        called["diagnose"] = True
        return _card()

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _diagnose)

    with pytest.raises(HTTPException) as ei:
        insights_ep.overview_summary(
            account_id=str(uuid.uuid4()),
            current_user=_owner("intruder-org"),
            db=object(),  # never touched: the guard raises before any query
            date_preset="last_30d",
            date_start=None, date_end=None, status=None, search=None,
        )
    assert ei.value.status_code == 403
    assert called["diagnose"] is False, "diagnosis generated for a forbidden account"


# ─── 2b. P-6 parity: diagnoser gets exactly what the read fns returned ───────


def test_summary_diagnoses_exact_read_dicts(monkeypatch):
    """P-6: the objects handed to generate_overview_diagnosis are byte-for-byte
    the ones the shared read functions returned for the same params — the
    handler must not recompute or mutate the numbers between read and diagnose.

    MOCKED:
      * the tenant guard → returns a fake account (no DB).
      * resolve_date_range → fixed range (no dependence on 'today').
      * get_overview / get_table / get_timeseries → return known objects.
      * generate_overview_diagnosis → captures the args it was passed.
    """
    account = _account()
    overview_obj, campaigns_obj, ts_obj = _stub_all_reads(monkeypatch, account=account)
    campaign_rows, _ = campaigns_obj  # get_table returns (rows, total)

    captured = {}

    def _diagnose(overview, acct, *, campaigns, timeseries):
        captured["overview"] = overview
        captured["account"] = acct
        captured["campaigns"] = campaigns
        captured["timeseries"] = timeseries
        return _card()

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _diagnose)

    resp = insights_ep.overview_summary(
        account_id="acct-1",
        current_user=_owner(),
        db=object(),
        date_preset="last_30d",
        date_start=None, date_end=None, status=None, search=None,
    )

    # Same object identity → provably no copy/recompute/mutation in between (P-6).
    assert captured["overview"] is overview_obj
    assert captured["overview"]["summary"] == overview_obj["summary"]
    assert captured["account"] is account
    # Campaigns passed are the ROWS from get_table (handler unpacks the tuple).
    assert captured["campaigns"] is campaign_rows
    # Timeseries passed is exactly what get_timeseries returned.
    assert captured["timeseries"] is ts_obj

    # Response carries all four structured fields (no more `narrative` blob).
    assert resp.headline == _card()["headline"]
    assert resp.driver == _card()["driver"]
    assert resp.watch == _card()["watch"]
    assert resp.next_step == _card()["next_step"]
    # P-1 envelope: the SAME period the numbers came from, plus model stamp.
    assert resp.period.date_start == overview_obj["period"]["date_start"]
    assert resp.period.date_stop == overview_obj["period"]["date_stop"]
    assert resp.model  # non-empty model identifier
    assert resp.generated_at is not None


# ─── 2c. AISummaryError → HTTP 502 (never a 200 with empty text) ─────────────


def test_summary_ai_failure_returns_502(monkeypatch):
    """P-4: if the OpenAI call fails, the endpoint returns a distinguishable 502
    with a detail — never a 200 carrying empty/fake diagnosis text.

    MOCKED: tenant guard + all three reads (no DB); generate_overview_diagnosis
    raises AISummaryError exactly as it does on any real OpenAI failure."""
    _stub_all_reads(monkeypatch, account=_account())

    def _boom(*a, **k):
        raise ai_summary_svc.AISummaryError("AI summary generation failed: upstream 500")

    monkeypatch.setattr(ai_summary_svc, "generate_overview_diagnosis", _boom)

    with pytest.raises(HTTPException) as ei:
        insights_ep.overview_summary(
            account_id="acct-1",
            current_user=_owner(),
            db=object(),
            date_preset="last_30d",
            date_start=None, date_end=None, status=None, search=None,
        )
    assert ei.value.status_code == 502
    assert ei.value.detail, "502 must carry a distinguishable detail, not be empty"
    assert ei.value.status_code != 200  # explicit: never a fake-success 200
