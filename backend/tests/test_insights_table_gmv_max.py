"""DB-backed tests for the GMV Max table wiring in the insights READ layer.

Gates the change per .claude/rules/test-required-for-done.md — it touches the
`metrics_daily` table query (a PRD §11 test-required area) and adds a new
response field + filter used to isolate TikTok GMV Max (`PRODUCT_SALES`)
campaigns from generic sales/conversion campaigns.

What changed in app/services/insights.py / endpoints/insights.py:
  1. TableRow now carries `platform_objective` (raw platform objective, e.g.
     TikTok "PRODUCT_SALES") alongside the normalized `objective` — both
     "PRODUCT_SALES" and "CONVERSIONS" normalize to "sales", so the raw value
     is what lets a caller pick out GMV Max campaigns.
  2. get_table / GET /insights/table gained an optional `platform_objective`
     filter (campaign level). When absent → no behavior change (all rows).

Pins:
  * platform_objective is surfaced on the row.
  * The filter returns ONLY matching campaigns and narrows total_count too.
  * Absent filter is a no-op (every campaign returned).
  * Tenant isolation: a cross-org org_id is a ForbiddenError (P — tenant
    isolation on every read path).
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.exceptions import ForbiddenError
from app.services.insights import get_overview, get_table

from tests.conftest import (
    insert_metrics_daily,
    make_account,
    make_connection,
    make_org,
)

CUR_START = date(2026, 6, 8)
CUR_END = date(2026, 6, 14)


def _make_campaign_obj(
    db, account_id: str, name: str, platform_objective: str,
    *, objective: str = "sales", status: str = "active",
) -> str:
    """A campaign with an explicit raw platform_objective (the conftest helper
    hard-codes objective and leaves platform_objective NULL, which is exactly
    what this suite needs to vary)."""
    camp_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO campaigns "
            "(id, account_id, platform_id, platform_campaign_id, name, status, "
            " effective_status, objective, platform_objective) "
            "VALUES (:id, :acct, 'meta', :pcid, :name, :status, :status, "
            " :obj, :pobj)"
        ),
        {
            "id": camp_id, "acct": uuid.UUID(account_id),
            "pcid": f"c_{camp_id.hex[:8]}", "name": name, "status": status,
            "obj": objective, "pobj": platform_objective,
        },
    )
    return str(camp_id)


def _seed_shop_and_generic(db):
    """One account with two 'sales' campaigns that differ ONLY by raw platform
    objective: a GMV Max (PRODUCT_SALES) one and a generic CONVERSIONS one.
    Both carry current-window spend so both appear in the table."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)

    gmv = _make_campaign_obj(db, account_id, "GMV Max Mukena", "PRODUCT_SALES")
    generic = _make_campaign_obj(db, account_id, "Generic Sales", "CONVERSIONS")

    insert_metrics_daily(db, account_id, gmv, CUR_START, impressions=1000, spend=200)
    insert_metrics_daily(db, account_id, generic, CUR_START, impressions=500, spend=100)
    db.flush()
    return {"org_id": org_id, "account_id": account_id, "gmv": gmv, "generic": generic}


def test_table_surfaces_platform_objective(db):
    """Each row exposes its raw platform_objective so the GMV Max view can flag
    PRODUCT_SALES campaigns."""
    ctx = _seed_shop_and_generic(db)
    rows, _ = get_table(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)
    by_name = {r["name"]: r for r in rows}
    assert by_name["GMV Max Mukena"]["platform_objective"] == "PRODUCT_SALES"
    assert by_name["Generic Sales"]["platform_objective"] == "CONVERSIONS"
    # Normalized objective can't distinguish them — both are "sales".
    assert by_name["GMV Max Mukena"]["objective"] == "sales"
    assert by_name["Generic Sales"]["objective"] == "sales"


def test_table_platform_objective_filter_returns_only_matching(db):
    """platform_objective='PRODUCT_SALES' returns ONLY the GMV Max campaign and
    narrows total_count to match (the filter is applied inside the SQL, so
    pagination reflects the scope)."""
    ctx = _seed_shop_and_generic(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        platform_objective="PRODUCT_SALES",
    )
    assert total == 1
    assert len(rows) == 1
    assert rows[0]["name"] == "GMV Max Mukena"
    assert rows[0]["platform_objective"] == "PRODUCT_SALES"


def test_table_no_platform_objective_filter_is_noop(db):
    """Absent filter → every campaign returned (no behavior change)."""
    ctx = _seed_shop_and_generic(db)
    rows, total = get_table(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)
    assert total == 2
    assert {r["name"] for r in rows} == {"GMV Max Mukena", "Generic Sales"}


def test_table_platform_objective_filter_no_match_is_empty(db):
    """A platform_objective with no campaigns → zero rows, zero total (an honest
    empty result, not an ignored filter)."""
    ctx = _seed_shop_and_generic(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        platform_objective="LEAD_GENERATION",
    )
    assert total == 0
    assert rows == []


def test_table_platform_objective_filter_cross_org_forbidden(db):
    """Tenant isolation: the GMV Max filter path still runs through the account
    access guard — a foreign org_id is a ForbiddenError, never a data leak."""
    ctx = _seed_shop_and_generic(db)
    other_org = make_org(db)
    db.flush()
    with pytest.raises(ForbiddenError):
        get_table(
            db, ctx["account_id"], other_org, CUR_START, CUR_END,
            platform_objective="PRODUCT_SALES",
        )


# ── Overview KPI scoping (parity with the GMV-Max-filtered table, P-6) ────────


def test_overview_platform_objective_scopes_kpis_to_gmv_max(db):
    """get_overview(platform_objective='PRODUCT_SALES') aggregates ONLY the GMV
    Max campaign's spend (200), never the generic CONVERSIONS one (100) — so the
    KPI cards match the GMV-Max-filtered table by construction."""
    ctx = _seed_shop_and_generic(db)
    s = get_overview(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        platform_objective="PRODUCT_SALES",
    )["summary"]
    assert s["spend"] == pytest.approx(200.0)


def test_overview_no_platform_objective_includes_all_campaigns(db):
    """Absent filter → account-wide totals (both campaigns): 200 + 100 = 300."""
    ctx = _seed_shop_and_generic(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]
    assert s["spend"] == pytest.approx(300.0)


def test_overview_platform_objective_no_match_is_zeroed(db):
    """A platform_objective with no campaigns → empty scope → no spend (honest
    empty, not the unfiltered total)."""
    ctx = _seed_shop_and_generic(db)
    s = get_overview(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        platform_objective="LEAD_GENERATION",
    )["summary"]
    assert not s["spend"]
