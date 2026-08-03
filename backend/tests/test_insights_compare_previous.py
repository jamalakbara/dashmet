"""DB-backed tests for the "Compare previous period" backend behavior.

Gates the feature per .claude/rules/test-required-for-done.md. Exercises the
real Postgres SQL path (arrays, date_trunc, FILTER) through the same seams the
API uses (`get_table` / `get_overview` on an `AsyncSession`-equivalent `Session`).

What's pinned here:
  * get_table(compare_previous=True) attaches a `metrics_previous` per row with
    the SAME key set as `metrics`, summed over resolve_prior_period(), with
    ratios computed AFTER aggregation (P-4 / anti-avg-of-averages).
  * The prior window used is exactly resolve_prior_period(date_start, date_end).
  * Entities with no prior data get metrics_previous present-but-null (no crash,
    row not dropped).
  * compare_previous=False (default) → no metrics_previous key at all.
  * get_overview always carries a `previous` summary (same keys as `summary`),
    populated from the prior window incl an action-based metric; `vs_previous`
    unchanged in shape.
  * Tenant isolation: cross-org get_table(compare_previous=True) → ForbiddenError
    (the endpoint maps this to 403).
"""
from datetime import date

import pytest

from app.exceptions import ForbiddenError
from app.services.insights import get_overview, get_table, resolve_prior_period

from tests.conftest import (
    insert_action_stat,
    insert_metrics_daily,
    make_account,
    make_campaign,
    make_connection,
    make_org,
)

# Current window: a 7-day span. Its prior window (equal-length, immediately
# before) is the 7 days ending the day before date_start.
CUR_START = date(2026, 6, 8)
CUR_END = date(2026, 6, 14)
PRIOR_START, PRIOR_END = resolve_prior_period(CUR_START, CUR_END)  # 2026-06-01..06-07


def _seed_two_period_campaign(db):
    """One org/account/campaign with metrics in BOTH windows, chosen so the
    prior-window ratios differ from the current-window ratios (catches a query
    that reuses the current window) and differ from a daily-average of ratios.
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="Alpha")

    # Current window: 2 days, uneven so avg-of-daily-ctr != aggregate-ctr.
    #   day1: 100 impr, 10 clicks  (daily ctr 10%)
    #   day2: 900 impr,  9 clicks  (daily ctr 1%)
    # aggregate ctr = 19 / 1000 * 100 = 1.9%   (avg of dailies would be 5.5%)
    insert_metrics_daily(db, account_id, camp_id, CUR_START,
                         impressions=100, clicks=10, spend=50, reach=80)
    insert_metrics_daily(db, account_id, camp_id, CUR_START.replace(day=9),
                         impressions=900, clicks=9, spend=150, reach=700)

    # Prior window: different totals, again uneven across two days.
    #   day1: 200 impr, 40 clicks  (daily ctr 20%)
    #   day2: 800 impr,  8 clicks  (daily ctr  1%)
    # aggregate ctr = 48 / 1000 * 100 = 4.8%   (avg of dailies would be 10.5%)
    insert_metrics_daily(db, account_id, camp_id, PRIOR_START,
                         impressions=200, clicks=40, spend=100, reach=150)
    insert_metrics_daily(db, account_id, camp_id, PRIOR_START.replace(day=2),
                         impressions=800, clicks=8, spend=300, reach=600)

    # Action metrics (purchases) in BOTH windows so action-derived values are
    # exercised end to end and the two summaries carry a symmetric key set:
    #   prior:   cost_per_purchase = prior_spend(400) / prior_purchases(10) = 40
    #   current: cost_per_purchase = curr_spend(200)  / curr_purchases(8)   = 25
    insert_action_stat(db, account_id, camp_id, PRIOR_START,
                       "actions", "purchase", 4)
    insert_action_stat(db, account_id, camp_id, PRIOR_START.replace(day=2),
                       "actions", "purchase", 6)  # prior purchases total = 10
    insert_action_stat(db, account_id, camp_id, CUR_START,
                       "actions", "purchase", 3)
    insert_action_stat(db, account_id, camp_id, CUR_START.replace(day=9),
                       "actions", "purchase", 5)  # current purchases total = 8

    db.flush()
    return {"org_id": org_id, "account_id": account_id, "campaign_id": camp_id}


# ─── get_table(compare_previous=True) ───────────────────────────────────────


def test_table_compare_previous_sums_base_metrics_over_prior_window(db):
    ctx = _seed_two_period_campaign(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        compare_previous=True,
    )
    assert total == 1
    row = rows[0]
    prev = row["metrics_previous"]

    # Base metrics summed over the PRIOR window only (200+800, 40+8, 100+300).
    assert prev["impressions"] == 1000
    assert prev["clicks"] == 48
    assert prev["spend"] == pytest.approx(400.0)
    assert prev["reach"] == 750

    # Sanity: current-window base metrics are the *current* totals, not prior.
    assert row["metrics"]["impressions"] == 1000
    assert row["metrics"]["clicks"] == 19
    assert row["metrics"]["spend"] == pytest.approx(200.0)


def test_table_compare_previous_ratios_are_aggregate_then_divide(db):
    """Prior ctr/cpm/cpc must be computed from prior SUMs, never averaged daily."""
    ctx = _seed_two_period_campaign(db)
    rows, _ = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        compare_previous=True,
    )
    prev = rows[0]["metrics_previous"]

    # ctr = sum(clicks)/sum(impr)*100 = 48/1000*100 = 4.8  (NOT avg(20,1)=10.5)
    assert prev["ctr"] == pytest.approx(4.8)
    # cpm = sum(spend)/sum(impr)*1000 = 400/1000*1000 = 400
    assert prev["cpm"] == pytest.approx(400.0)
    # cpc = sum(spend)/sum(clicks) = 400/48
    assert prev["cpc"] == pytest.approx(400.0 / 48)

    # Action-derived prior ratio: cost_per_purchase = prior_spend/prior_purchases
    # = 400 / 10 = 40.0 — computed after aggregation in _finalize_metrics.
    assert prev["cost_per_purchase"] == pytest.approx(40.0)


def test_table_prior_window_equals_resolve_prior_period(db):
    """The prior data used must be the resolve_prior_period() window, nothing
    else: a row placed one day outside that window must NOT be counted."""
    ctx = _seed_two_period_campaign(db)
    account_id, camp_id = ctx["account_id"], ctx["campaign_id"]

    # A day immediately BEFORE the prior window (should be excluded).
    before = date(2026, 5, 31)
    assert before < PRIOR_START
    insert_metrics_daily(db, account_id, camp_id, before,
                         impressions=100000, clicks=100000, spend=99999)
    db.flush()

    rows, _ = get_table(
        db, account_id, ctx["org_id"], CUR_START, CUR_END, compare_previous=True,
    )
    prev = rows[0]["metrics_previous"]
    # Unchanged from the in-window totals — the out-of-window day was ignored.
    assert prev["impressions"] == 1000
    assert prev["clicks"] == 48


def test_table_previous_has_same_keys_as_current_metrics(db):
    ctx = _seed_two_period_campaign(db)
    rows, _ = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        compare_previous=True,
    )
    row = rows[0]
    assert set(row["metrics_previous"].keys()) == set(row["metrics"].keys())


def test_table_missing_prior_data_yields_null_metrics_not_dropped(db):
    """An entity with current data but NO prior data keeps its row and gets a
    metrics_previous of nulls (present, same keys) — not omitted, not a crash."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="CurrentOnly")

    # Current window only.
    insert_metrics_daily(db, account_id, camp_id, CUR_START,
                         impressions=500, clicks=25, spend=75)
    db.flush()

    rows, total = get_table(
        db, account_id, org_id, CUR_START, CUR_END, compare_previous=True,
    )
    assert total == 1
    row = rows[0]
    assert "metrics_previous" in row
    prev = row["metrics_previous"]
    assert set(prev.keys()) == set(row["metrics"].keys())
    # No prior rows → every prior value is null.
    assert prev["impressions"] is None
    assert prev["clicks"] is None
    assert prev["spend"] is None
    assert prev["ctr"] is None
    assert prev["cost_per_purchase"] is None
    # Current row still fully populated.
    assert row["metrics"]["impressions"] == 500


def test_table_compare_previous_false_omits_previous_key(db):
    ctx = _seed_two_period_campaign(db)
    rows, _ = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
        # compare_previous defaults to False
    )
    assert rows
    for row in rows:
        assert "metrics_previous" not in row


# ─── get_overview ───────────────────────────────────────────────────────────


def test_overview_previous_same_keys_as_summary_and_populated(db):
    ctx = _seed_two_period_campaign(db)
    out = get_overview(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
    )
    assert "summary" in out and "previous" in out
    summary, previous = out["summary"], out["previous"]

    # Full previous summary with the SAME key set as the current summary.
    assert set(previous.keys()) == set(summary.keys())

    # Populated from the prior window: prior base totals + a prior action metric.
    assert previous["impressions"] == 1000
    assert previous["clicks"] == 48
    assert previous["ctr"] == pytest.approx(4.8)  # aggregate-then-divide
    # Action-derived prior metric present (cost_per_purchase = 400/10).
    assert previous["cost_per_purchase"] == pytest.approx(40.0)

    # Current summary is the current window (distinct from previous).
    assert summary["impressions"] == 1000
    assert summary["clicks"] == 19
    assert summary["ctr"] == pytest.approx(1.9)


def test_overview_vs_previous_shape_unchanged(db):
    ctx = _seed_two_period_campaign(db)
    out = get_overview(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END,
    )
    assert "vs_previous" in out
    vs = out["vs_previous"]
    expected_keys = {
        "spend", "impressions", "clicks", "ctr", "cpm", "conversions",
        "roas", "outbound_clicks", "outbound_clicks_ctr",
    }
    assert set(vs.keys()) == expected_keys
    # spend rose 200 vs 400 → -50% change, sanity that it's still a pct number.
    assert vs["spend"] == pytest.approx(-50.0)


# ─── Tenant isolation ───────────────────────────────────────────────────────


def test_table_compare_previous_cross_org_forbidden(db):
    """A caller from org B cannot read org A's table even with compare_previous —
    assert_account_belongs_to_org raises ForbiddenError (endpoint → 403)."""
    ctx = _seed_two_period_campaign(db)
    other_org_id = make_org(db, name="Intruder")
    db.flush()

    with pytest.raises(ForbiddenError):
        get_table(
            db, ctx["account_id"], other_org_id, CUR_START, CUR_END,
            compare_previous=True,
        )
