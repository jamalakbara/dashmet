"""Coverage for the Meta CPAS "Shared Item" (catalog-segment) metrics in the
insights READ layer.

Gates the change per .claude/rules/test-required-for-done.md — it touches
`metric_action_stats` aggregation, a PRD §11 test-required area, and derives
ratios (roas_shared, cost_per_*_shared) that MUST be computed after aggregation
(P-7), never as an average of per-row ratios.

What changed in app/services/insights.py:
  1. `_ACTION_PIVOT_COLS` gained 5 SQL FILTER columns pivoted out of
     metric_action_stats:
       * purchase_shared          = SUM WHERE field_name='catalog_segment_actions'
                                            AND action_type='purchase'
       * add_to_cart_shared       = SUM WHERE field_name='catalog_segment_actions'
                                            AND action_type='add_to_cart'
       * content_view_shared      = SUM WHERE field_name='catalog_segment_actions'
                                            AND action_type='view_content'
       * purchase_value_shared    = SUM WHERE field_name='catalog_segment_value'
                                            AND action_type='purchase'
       * add_to_cart_value_shared = SUM WHERE field_name='catalog_segment_value'
                                            AND action_type='add_to_cart'
  2. purchase_shared/add_to_cart_shared/content_view_shared are int keys
     (_ACTION_INT_KEYS); purchase_value_shared/add_to_cart_value_shared are
     float keys (_ACTION_FLOAT_KEYS).
  3. `_finalize_metrics` derives (after aggregation, never stored):
       * cost_per_purchase_shared      = round(spend / purchase_shared, 4)
       * cost_per_add_to_cart_shared   = round(spend / add_to_cart_shared, 4)
       * cost_per_content_view_shared  = round(spend / content_view_shared, 4)
       * roas_shared                   = round(purchase_value_shared / spend, 4)

Two layers of tests (mirrors test_insights_meta_metrics.py):
  * Pure-Python unit tests for `_finalize_metrics` and `_action_dict` — no DB,
    always run here.
  * DB-backed pivot tests exercising the real Postgres FILTER/SUM path through
    `get_overview` / `get_table`. These need a live Postgres 16 (the `db`
    fixture); where no DB host is reachable they error at fixture setup rather
    than run.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.services.insights import (
    _ACTION_FLOAT_KEYS,
    _ACTION_INT_KEYS,
    _action_dict,
    _finalize_metrics,
    get_overview,
    get_table,
    resolve_prior_period,
)

from tests.conftest import (
    insert_action_stat,
    insert_metrics_daily,
    make_account,
    make_campaign,
    make_connection,
    make_org,
)


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python unit tests — no DB required.
# ─────────────────────────────────────────────────────────────────────────────


# ── _finalize_metrics: cost_per_*_shared ────────────────────────────────────


def test_cost_per_purchase_shared_spend_over_purchase():
    """spend=100, purchase_shared=4 → cost_per_purchase_shared=25.0."""
    m = _finalize_metrics({"spend": 100, "purchase_shared": 4})
    assert m["cost_per_purchase_shared"] == 25.0


def test_cost_per_add_to_cart_shared_spend_over_atc():
    """spend=100, add_to_cart_shared=8 → 12.5."""
    m = _finalize_metrics({"spend": 100, "add_to_cart_shared": 8})
    assert m["cost_per_add_to_cart_shared"] == 12.5


def test_cost_per_content_view_shared_spend_over_view():
    """spend=100, content_view_shared=40 → 2.5."""
    m = _finalize_metrics({"spend": 100, "content_view_shared": 40})
    assert m["cost_per_content_view_shared"] == 2.5


def test_roas_shared_value_over_spend():
    """spend=100, purchase_value_shared=300 → roas_shared=3.0."""
    m = _finalize_metrics({"spend": 100, "purchase_value_shared": 300})
    assert m["roas_shared"] == 3.0


def test_cpas_ratios_round_to_four_decimals():
    """Every CPAS ratio uses the 4dp rounding convention (like ROAS/CPA)."""
    # spend/purchase_shared = 100/3 = 33.3333...
    m = _finalize_metrics({"spend": 100, "purchase_shared": 3})
    assert m["cost_per_purchase_shared"] == pytest.approx(33.3333)
    # value/spend = 100/3 = 33.3333...
    m2 = _finalize_metrics({"spend": 3, "purchase_value_shared": 100})
    assert m2["roas_shared"] == pytest.approx(33.3333)


# ── None / zero guards (P-4: refuse to answer rather than answer wrong) ──────


def test_cost_per_purchase_shared_zero_denominator_is_none():
    """purchase_shared=0 → None (no divide-by-zero, no fake number)."""
    m = _finalize_metrics({"spend": 100, "purchase_shared": 0})
    assert m["cost_per_purchase_shared"] is None


def test_cost_per_purchase_shared_none_denominator_is_none():
    """purchase_shared missing/None → None."""
    m = _finalize_metrics({"spend": 100, "purchase_shared": None})
    assert m["cost_per_purchase_shared"] is None
    m2 = _finalize_metrics({"spend": 100})
    assert m2["cost_per_purchase_shared"] is None


def test_cost_per_shared_metrics_none_spend_is_none():
    """spend missing/None (or 0) → every cost_per_*_shared is None."""
    for spend in (None, 0):
        m = _finalize_metrics(
            {
                "spend": spend,
                "purchase_shared": 4,
                "add_to_cart_shared": 8,
                "content_view_shared": 40,
            }
        )
        assert m["cost_per_purchase_shared"] is None
        assert m["cost_per_add_to_cart_shared"] is None
        assert m["cost_per_content_view_shared"] is None


def test_roas_shared_zero_or_none_spend_is_none():
    """spend=0 or None → roas_shared None (denominator guard)."""
    for spend in (None, 0):
        m = _finalize_metrics({"spend": spend, "purchase_value_shared": 300})
        assert m["roas_shared"] is None


def test_roas_shared_none_value_is_none():
    """purchase_value_shared missing/None → roas_shared None (numerator guard)."""
    m = _finalize_metrics({"spend": 100, "purchase_value_shared": None})
    assert m["roas_shared"] is None
    m2 = _finalize_metrics({"spend": 100})
    assert m2["roas_shared"] is None


def test_cpas_derived_keys_present_on_empty_metric_dict():
    """An empty metric dict → all CPAS derived keys present and None (honest
    absence, key still emitted so the response envelope is stable, P-1)."""
    m = _finalize_metrics({})
    for k in (
        "cost_per_purchase_shared",
        "cost_per_add_to_cart_shared",
        "cost_per_content_view_shared",
        "roas_shared",
    ):
        assert k in m
        assert m[k] is None


def test_cpas_ratios_do_not_disturb_neighbouring_derived_metrics():
    """Adding the CPAS ratios didn't break the standard cost_per_purchase / roas
    (shared vs non-shared are independent code paths on the same dict)."""
    m = _finalize_metrics(
        {
            "spend": 100,
            "purchase": 5,
            "purchase_shared": 4,
            "purchase_value_shared": 300,
        }
    )
    # Standard (non-shared) path unchanged.
    assert m["cost_per_purchase"] == 20.0
    # Shared path.
    assert m["cost_per_purchase_shared"] == 25.0
    assert m["roas_shared"] == 3.0


# ── Ratio-after-aggregation invariant (P-7 / PRD §11) ────────────────────────


def test_roas_shared_is_ratio_after_aggregation_not_avg_of_rows():
    """roas_shared must be SUM(value) ÷ SUM(spend) across rows, NOT the average
    of per-row ROAS.

    Two days with uneven spend so the two computations diverge sharply:
      day1: value=100, spend=10   → per-row roas 10.0
      day2: value=100, spend=90   → per-row roas 1.1111
    avg-of-rows would be (10.0 + 1.1111)/2 = 5.5556.
    Correct aggregate = sum(value)/sum(spend) = 200/100 = 2.0.

    `_finalize_metrics` only ever sees the already-summed totals, so it CANNOT
    produce the avg-of-rows value — this pins that the summed inputs divide to
    2.0 and are nowhere near the 5.5556 avg-of-averages trap.
    """
    summed_value = 100 + 100
    summed_spend = 10 + 90
    m = _finalize_metrics(
        {"spend": summed_spend, "purchase_value_shared": summed_value}
    )
    assert m["roas_shared"] == 2.0
    avg_of_rows = ((100 / 10) + (100 / 90)) / 2  # 5.5556
    assert m["roas_shared"] != pytest.approx(avg_of_rows)


def test_cost_per_purchase_shared_is_ratio_after_aggregation_not_avg_of_rows():
    """cost_per_purchase_shared must be SUM(spend) ÷ SUM(purchase_shared), NOT
    the average of per-row cost-per-purchase.

    Two days with uneven spend/purchases:
      day1: spend=100, purchases=1   → per-row cpp 100.0
      day2: spend=100, purchases=9   → per-row cpp 11.1111
    avg-of-rows would be (100.0 + 11.1111)/2 = 55.5556.
    Correct aggregate = sum(spend)/sum(purchases) = 200/10 = 20.0.
    """
    summed_spend = 100 + 100
    summed_purchases = 1 + 9
    m = _finalize_metrics(
        {"spend": summed_spend, "purchase_shared": summed_purchases}
    )
    assert m["cost_per_purchase_shared"] == 20.0
    avg_of_rows = ((100 / 1) + (100 / 9)) / 2  # 55.5556
    assert m["cost_per_purchase_shared"] != pytest.approx(avg_of_rows)


# ── _action_dict + key-registration typing ──────────────────────────────────


def test_cpas_action_keys_registered_with_correct_typing():
    """purchase_shared/add_to_cart_shared/content_view_shared are integer keys;
    purchase_value_shared/add_to_cart_value_shared are float keys."""
    assert "purchase_shared" in _ACTION_INT_KEYS
    assert "add_to_cart_shared" in _ACTION_INT_KEYS
    assert "content_view_shared" in _ACTION_INT_KEYS
    assert "purchase_value_shared" in _ACTION_FLOAT_KEYS
    assert "add_to_cart_value_shared" in _ACTION_FLOAT_KEYS
    # And not cross-registered (value metrics never coerced to int, counts never
    # coerced to float).
    assert "purchase_shared" not in _ACTION_FLOAT_KEYS
    assert "add_to_cart_shared" not in _ACTION_FLOAT_KEYS
    assert "content_view_shared" not in _ACTION_FLOAT_KEYS
    assert "purchase_value_shared" not in _ACTION_INT_KEYS
    assert "add_to_cart_value_shared" not in _ACTION_INT_KEYS


def test_action_dict_coerces_cpas_metrics_to_right_python_type():
    """A pivot row (Numeric values → Decimal) becomes int for the shared counts
    and float for the shared values.

    metric_action_stats.value is Numeric(18,4), so the pivot SUM comes back as a
    Decimal-like; _action_dict must coerce the *_shared counts to int and the
    *_value_shared amounts to float."""
    row = {
        "purchase_shared": Decimal("4"),
        "add_to_cart_shared": Decimal("8"),
        "content_view_shared": Decimal("40"),
        "purchase_value_shared": Decimal("300.5000"),
        "add_to_cart_value_shared": Decimal("125.2500"),
    }
    out = _action_dict(row)

    assert out["purchase_shared"] == 4
    assert isinstance(out["purchase_shared"], int)
    assert out["add_to_cart_shared"] == 8
    assert isinstance(out["add_to_cart_shared"], int)
    assert out["content_view_shared"] == 40
    assert isinstance(out["content_view_shared"], int)

    assert out["purchase_value_shared"] == pytest.approx(300.5)
    assert isinstance(out["purchase_value_shared"], float)
    assert out["add_to_cart_value_shared"] == pytest.approx(125.25)
    assert isinstance(out["add_to_cart_value_shared"], float)


def test_action_dict_missing_cpas_metrics_are_none():
    """A row with no catalog_segment rows → None, not 0 (honest absence,
    P-1/P-4)."""
    out = _action_dict({"purchase": 5})  # unrelated (non-shared) key only
    assert out["purchase_shared"] is None
    assert out["add_to_cart_shared"] is None
    assert out["content_view_shared"] is None
    assert out["purchase_value_shared"] is None
    assert out["add_to_cart_value_shared"] is None


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed pivot tests — require a live Postgres 16 (the `db` fixture).
# ─────────────────────────────────────────────────────────────────────────────

# A 7-day current window (mirrors the existing compare-previous / meta-metrics
# suites so the seeding pattern is identical).
CUR_START = date(2026, 6, 8)
CUR_END = date(2026, 6, 14)
PRIOR_START, PRIOR_END = resolve_prior_period(CUR_START, CUR_END)


def _seed_cpas_metrics(db):
    """One org/account/campaign with catalog-segment action + value rows across
    TWO days in the current window, plus base spend so the derived cost/ROAS
    ratios are exercised end-to-end from summed inputs.

    Current window (2 days):
      day1 (Jun 8): purchase_shared=3, add_to_cart_shared=5, content_view_shared=20,
                    purchase_value_shared=200, add_to_cart_value_shared=60, spend=200
      day2 (Jun 9): purchase_shared=1, add_to_cart_shared=3, content_view_shared=10,
                    purchase_value_shared=100, add_to_cart_value_shared=40, spend=100
    Sums: purchase_shared=4, add_to_cart_shared=8, content_view_shared=30,
          purchase_value_shared=300, add_to_cart_value_shared=100, spend=300
    Derived: cost_per_purchase_shared=300/4=75.0,
             cost_per_add_to_cart_shared=300/8=37.5,
             cost_per_content_view_shared=300/30=10.0,
             roas_shared=300/300=1.0
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="CpasAlpha")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)

    insert_metrics_daily(db, account_id, camp_id, day1,
                         impressions=1000, clicks=50, spend=200, reach=800)
    insert_metrics_daily(db, account_id, camp_id, day2,
                         impressions=500, clicks=25, spend=100, reach=400)

    # catalog_segment_actions (counts) split across the two days so the pivot SUMs.
    insert_action_stat(db, account_id, camp_id, day1,
                       "catalog_segment_actions", "purchase", 3)
    insert_action_stat(db, account_id, camp_id, day2,
                       "catalog_segment_actions", "purchase", 1)
    insert_action_stat(db, account_id, camp_id, day1,
                       "catalog_segment_actions", "add_to_cart", 5)
    insert_action_stat(db, account_id, camp_id, day2,
                       "catalog_segment_actions", "add_to_cart", 3)
    insert_action_stat(db, account_id, camp_id, day1,
                       "catalog_segment_actions", "view_content", 20)
    insert_action_stat(db, account_id, camp_id, day2,
                       "catalog_segment_actions", "view_content", 10)

    # catalog_segment_value (amounts).
    insert_action_stat(db, account_id, camp_id, day1,
                       "catalog_segment_value", "purchase", 200)
    insert_action_stat(db, account_id, camp_id, day2,
                       "catalog_segment_value", "purchase", 100)
    insert_action_stat(db, account_id, camp_id, day1,
                       "catalog_segment_value", "add_to_cart", 60)
    insert_action_stat(db, account_id, camp_id, day2,
                       "catalog_segment_value", "add_to_cart", 40)

    db.flush()
    return {"org_id": org_id, "account_id": account_id, "campaign_id": camp_id}


# ── Pivot correctness through get_overview ──────────────────────────────────


def test_overview_pivots_and_sums_cpas_metrics(db):
    """The 5 CPAS columns are pivoted from metric_action_stats and SUMMED across
    the two days, with correct typing (int counts, float values)."""
    ctx = _seed_cpas_metrics(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]

    assert s["purchase_shared"] == 4
    assert isinstance(s["purchase_shared"], int)
    assert s["add_to_cart_shared"] == 8
    assert isinstance(s["add_to_cart_shared"], int)
    assert s["content_view_shared"] == 30
    assert isinstance(s["content_view_shared"], int)

    assert s["purchase_value_shared"] == pytest.approx(300.0)
    assert isinstance(s["purchase_value_shared"], float)
    assert s["add_to_cart_value_shared"] == pytest.approx(100.0)
    assert isinstance(s["add_to_cart_value_shared"], float)


def test_overview_cpas_derived_ratios_from_summed_inputs(db):
    """cost_per_*_shared and roas_shared derived after aggregation:
      cost_per_purchase_shared     = spend/purchase_shared     = 300/4  = 75.0
      cost_per_add_to_cart_shared  = spend/add_to_cart_shared  = 300/8  = 37.5
      cost_per_content_view_shared = spend/content_view_shared = 300/30 = 10.0
      roas_shared                  = value/spend               = 300/300 = 1.0
    """
    ctx = _seed_cpas_metrics(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]

    assert s["spend"] == pytest.approx(300.0)
    assert s["cost_per_purchase_shared"] == pytest.approx(75.0)
    assert s["cost_per_add_to_cart_shared"] == pytest.approx(37.5)
    assert s["cost_per_content_view_shared"] == pytest.approx(10.0)
    assert s["roas_shared"] == pytest.approx(1.0)
    # Structural: roas_shared equals summed_value / summed_spend exactly.
    assert s["roas_shared"] == pytest.approx(
        s["purchase_value_shared"] / s["spend"]
    )


def test_overview_cpas_isolate_by_action_type_and_field_name(db):
    """The FILTER predicates only sum their own field_name/action_type. Two leaks
    are specifically guarded:

      1. A catalog_segment_actions/purchase row must NOT land in add_to_cart_shared
         (action_type isolation within the same field_name).
      2. A regular actions/purchase row must NOT leak into purchase_shared
         (field_name isolation — 'actions' vs 'catalog_segment_actions').
    """
    ctx = _seed_cpas_metrics(db)
    # Noise: a regular (non-CPAS) purchase COUNT and value — these belong to the
    # standard 'purchase'/'conversion_value' metrics, never to *_shared.
    insert_action_stat(db, ctx["account_id"], ctx["campaign_id"], CUR_START,
                       "actions", "purchase", 999)
    insert_action_stat(db, ctx["account_id"], ctx["campaign_id"], CUR_START,
                       "action_values", "purchase", 777)
    # Noise: an unrelated catalog_segment action_type that maps to no column.
    insert_action_stat(db, ctx["account_id"], ctx["campaign_id"], CUR_START,
                       "catalog_segment_actions", "lead", 888)
    db.flush()

    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]
    # CPAS columns unchanged despite the noise rows.
    assert s["purchase_shared"] == 4          # not 4+999
    assert s["add_to_cart_shared"] == 8       # catalog purchase did not leak here
    assert s["content_view_shared"] == 30
    assert s["purchase_value_shared"] == pytest.approx(300.0)  # not 300+777
    # And the regular purchase still flows to its own (non-shared) column.
    assert s["purchase"] == 999


def test_overview_cpas_ratios_aggregate_not_avg_of_rows_db(db):
    """DB-level ratio-after-aggregation invariant (P-7) for roas_shared.

    Uneven per-day spend so avg-of-rows != aggregate:
      day1: value=100, spend=10  → per-day roas 10.0
      day2: value=100, spend=90  → per-day roas 1.1111
    aggregate = 200/100 = 2.0 ; avg-of-rows = 5.5556.
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="CpasUneven")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)
    insert_metrics_daily(db, account_id, camp_id, day1, impressions=10, spend=10)
    insert_metrics_daily(db, account_id, camp_id, day2, impressions=10, spend=90)
    insert_action_stat(db, account_id, camp_id, day1,
                       "catalog_segment_value", "purchase", 100)
    insert_action_stat(db, account_id, camp_id, day2,
                       "catalog_segment_value", "purchase", 100)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["spend"] == pytest.approx(100.0)
    assert s["purchase_value_shared"] == pytest.approx(200.0)
    assert s["roas_shared"] == pytest.approx(2.0)
    avg_of_rows = ((100 / 10) + (100 / 90)) / 2  # 5.5556
    assert s["roas_shared"] != pytest.approx(avg_of_rows)


def test_overview_no_cpas_rows_yields_null_not_zero(db):
    """A window with base metrics but no catalog_segment rows → every *_shared
    key is null and every derived CPAS ratio is null (P-1/P-4)."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="CpasBaseOnly")
    insert_metrics_daily(db, account_id, camp_id, CUR_START,
                         impressions=100, clicks=5, spend=20)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["purchase_shared"] is None
    assert s["add_to_cart_shared"] is None
    assert s["content_view_shared"] is None
    assert s["purchase_value_shared"] is None
    assert s["add_to_cart_value_shared"] is None
    assert s["cost_per_purchase_shared"] is None
    assert s["cost_per_add_to_cart_shared"] is None
    assert s["cost_per_content_view_shared"] is None
    assert s["roas_shared"] is None


# ── Pivot correctness through get_table (per-entity SUM) ─────────────────────


def test_table_pivots_cpas_metrics_per_entity(db):
    """get_table pivots the same 5 CPAS columns per entity, summed over the
    window, and derives the CPAS ratios per row after aggregation."""
    ctx = _seed_cpas_metrics(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END, level="campaign",
    )
    assert total == 1
    m = rows[0]["metrics"]
    assert m["purchase_shared"] == 4
    assert m["add_to_cart_shared"] == 8
    assert m["content_view_shared"] == 30
    assert m["purchase_value_shared"] == pytest.approx(300.0)
    assert m["add_to_cart_value_shared"] == pytest.approx(100.0)
    # Derived from spend (300) after aggregation.
    assert m["cost_per_purchase_shared"] == pytest.approx(75.0)
    assert m["cost_per_add_to_cart_shared"] == pytest.approx(37.5)
    assert m["cost_per_content_view_shared"] == pytest.approx(10.0)
    assert m["roas_shared"] == pytest.approx(1.0)


def test_table_cpas_summed_across_entities_independently(db):
    """Two campaigns in the same window: each entity's pivot sums only its own
    catalog_segment rows (no cross-entity bleed)."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_a = make_campaign(db, account_id, name="A")
    camp_b = make_campaign(db, account_id, name="B")

    insert_metrics_daily(db, account_id, camp_a, CUR_START, impressions=100, spend=10)
    insert_metrics_daily(db, account_id, camp_b, CUR_START, impressions=100, spend=10)
    insert_action_stat(db, account_id, camp_a, CUR_START,
                       "catalog_segment_actions", "purchase", 7)
    insert_action_stat(db, account_id, camp_b, CUR_START,
                       "catalog_segment_actions", "purchase", 2)
    insert_action_stat(db, account_id, camp_a, CUR_START,
                       "catalog_segment_value", "purchase", 30.5)
    db.flush()

    rows, _ = get_table(db, account_id, org_id, CUR_START, CUR_END, level="campaign")
    by_name = {r["name"]: r["metrics"] for r in rows}
    assert by_name["A"]["purchase_shared"] == 7
    assert by_name["A"]["purchase_value_shared"] == pytest.approx(30.5)
    assert by_name["B"]["purchase_shared"] == 2
    # B has no catalog_segment_value row → null, not A's value.
    assert by_name["B"]["purchase_value_shared"] is None
