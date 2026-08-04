"""Coverage for the 4 Meta metrics added to the insights READ layer.

Gates the change per .claude/rules/test-required-for-done.md — it touches
`metric_action_stats` aggregation, a PRD §11 test-required area.

What changed in app/services/insights.py:
  1. `_ACTION_PIVOT_COLS` gained 3 SQL FILTER columns pivoted out of
     metric_action_stats:
       * post_reactions     = SUM WHERE field_name='actions'
                                       AND action_type='post_reaction'
       * post_saves         = SUM WHERE field_name='actions'
                                       AND action_type='onsite_conversion.post_save'
       * add_to_cart_value  = SUM WHERE field_name='action_values'
                                       AND action_type='add_to_cart'
  2. post_reactions/post_saves are int keys (_ACTION_INT_KEYS);
     add_to_cart_value is a float key (_ACTION_FLOAT_KEYS).
  3. `_finalize_metrics` derives avg_basket_price = round(conversion_value /
     purchase, 4) when both present, else None.

Two layers of tests:
  * Pure-Python unit tests for `_finalize_metrics` and `_action_dict` — no DB,
    always run here.
  * DB-backed pivot tests exercising the real Postgres FILTER/SUM path through
    `get_overview` / `get_table`, following the test_insights_compare_previous
    seeding pattern. These need a live Postgres 16 (the `db` fixture); where no
    DB host is reachable they error at fixture setup rather than run.
"""
from datetime import date

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


# ── _finalize_metrics: avg_basket_price ─────────────────────────────────────


def test_avg_basket_price_conversion_value_over_purchase():
    """conversion_value=100, purchase=4 → 25.0 (Purchase Value ÷ Purchase)."""
    m = _finalize_metrics({"conversion_value": 100, "purchase": 4})
    assert m["avg_basket_price"] == 25.0


def test_avg_basket_price_rounds_to_four_decimals():
    """Result is rounded to 4dp, matching the ROAS/CPA rounding convention."""
    m = _finalize_metrics({"conversion_value": 100, "purchase": 3})
    # 100/3 = 33.3333... → 33.3333
    assert m["avg_basket_price"] == pytest.approx(33.3333)


def test_avg_basket_price_purchase_zero_is_none():
    """purchase=0 → None (no divide-by-zero, no fake number). P-4."""
    m = _finalize_metrics({"conversion_value": 100, "purchase": 0})
    assert m["avg_basket_price"] is None


def test_avg_basket_price_purchase_none_is_none():
    """purchase missing/None → None (honest absence, not 0)."""
    m = _finalize_metrics({"conversion_value": 100, "purchase": None})
    assert m["avg_basket_price"] is None
    m2 = _finalize_metrics({"conversion_value": 100})
    assert m2["avg_basket_price"] is None


def test_avg_basket_price_conversion_value_none_is_none():
    """conversion_value missing/None → None. Guards timeseries points that lack
    conversion_value entirely."""
    m = _finalize_metrics({"conversion_value": None, "purchase": 4})
    assert m["avg_basket_price"] is None
    m2 = _finalize_metrics({"purchase": 4})
    assert m2["avg_basket_price"] is None


def test_avg_basket_price_both_missing_is_none():
    """An empty metric dict (e.g. a null prior-window row) → avg_basket_price None,
    key still present."""
    m = _finalize_metrics({})
    assert "avg_basket_price" in m
    assert m["avg_basket_price"] is None


def test_avg_basket_price_is_ratio_after_aggregation_not_avg_of_rows():
    """PRD §11 / P-7 invariant: avg_basket_price is summed_value ÷ summed_purchase,
    NOT the average of per-row basket prices.

    Two days:
      day1: value=100, purchase=1  → per-row basket 100
      day2: value=100, purchase=9  → per-row basket 11.11
    avg-of-rows would be (100 + 11.11)/2 = 55.56.
    Correct aggregate = sum(value)/sum(purchase) = 200/10 = 20.0.

    `_finalize_metrics` only ever sees the already-summed totals, so it CANNOT
    produce the avg-of-rows value — this pins that the summed inputs divide to
    20.0 and are nowhere near the 55.56 avg-of-averages trap.
    """
    summed_value = 100 + 100
    summed_purchase = 1 + 9
    m = _finalize_metrics(
        {"conversion_value": summed_value, "purchase": summed_purchase}
    )
    assert m["avg_basket_price"] == 20.0
    # Explicitly distinct from the avg-of-per-row-basket-prices mistake.
    avg_of_rows = ((100 / 1) + (100 / 9)) / 2
    assert m["avg_basket_price"] != pytest.approx(avg_of_rows)


def test_avg_basket_price_does_not_disturb_other_derived_metrics():
    """Adding avg_basket_price didn't break neighbouring derived ratios."""
    m = _finalize_metrics(
        {"spend": 50, "purchase": 5, "conversion_value": 100}
    )
    assert m["avg_basket_price"] == 20.0
    # cost_per_purchase = spend/purchase = 50/5 = 10.0 (unchanged path).
    assert m["cost_per_purchase"] == 10.0


# ── _action_dict + key-registration typing ──────────────────────────────────


def test_new_action_keys_registered_with_correct_typing():
    """post_reactions/post_saves are integer keys; add_to_cart_value is float."""
    assert "post_reactions" in _ACTION_INT_KEYS
    assert "post_saves" in _ACTION_INT_KEYS
    assert "add_to_cart_value" in _ACTION_FLOAT_KEYS
    # And not cross-registered.
    assert "add_to_cart_value" not in _ACTION_INT_KEYS
    assert "post_reactions" not in _ACTION_FLOAT_KEYS
    assert "post_saves" not in _ACTION_FLOAT_KEYS


def test_action_dict_coerces_new_metrics_to_right_python_type():
    """A pivot row (Numeric values) becomes int for counts, float for value.

    metric_action_stats.value is Numeric(18,4), so the pivot SUM comes back as a
    Decimal-like; _action_dict must coerce post_reactions/post_saves to int and
    add_to_cart_value to float."""
    from decimal import Decimal

    row = {
        "post_reactions": Decimal("12"),
        "post_saves": Decimal("3"),
        "add_to_cart_value": Decimal("456.7800"),
    }
    out = _action_dict(row)

    assert out["post_reactions"] == 12
    assert isinstance(out["post_reactions"], int)
    assert out["post_saves"] == 3
    assert isinstance(out["post_saves"], int)
    assert out["add_to_cart_value"] == pytest.approx(456.78)
    assert isinstance(out["add_to_cart_value"], float)


def test_action_dict_missing_new_metrics_are_none():
    """A row with no post_reaction/post_save/add_to_cart_value rows → None, not 0
    (honest absence, P-1/P-4)."""
    out = _action_dict({"add_to_cart": 5})  # unrelated key only
    assert out["post_reactions"] is None
    assert out["post_saves"] is None
    assert out["add_to_cart_value"] is None


def test_action_dict_empty_row_returns_empty_dict():
    assert _action_dict(None) == {}
    assert _action_dict({}) == {}


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed pivot tests — require a live Postgres 16 (the `db` fixture).
# ─────────────────────────────────────────────────────────────────────────────

# A 7-day current window and its resolved prior window (mirrors the existing
# compare-previous suite).
CUR_START = date(2026, 6, 8)
CUR_END = date(2026, 6, 14)
PRIOR_START, PRIOR_END = resolve_prior_period(CUR_START, CUR_END)


def _seed_new_meta_metrics(db):
    """One org/account/campaign with post_reaction, post_save, add_to_cart_value
    rows across TWO days in the current window, plus purchase + conversion_value
    rows so avg_basket_price is exercised end-to-end from summed inputs.

    Current window (2 days), chosen so summed inputs are unambiguous:
      day1 (Jun 8):  post_reaction=10, post_save=2, add_to_cart_value=100.50,
                     purchase=3,  action_values/purchase (revenue)=300
      day2 (Jun 9):  post_reaction=5,  post_save=4, add_to_cart_value=49.50,
                     purchase=1,  action_values/purchase (revenue)=100
    Sums: post_reactions=15, post_saves=6, add_to_cart_value=150.00,
          purchases=4, conversion_value=400 → avg_basket_price=100.0
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="Alpha")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)

    # Base metrics so metrics_daily has rows in the window (spend used by
    # neighbouring derived metrics; irrelevant to the pivot itself).
    insert_metrics_daily(db, account_id, camp_id, day1,
                         impressions=1000, clicks=50, spend=200, reach=800)
    insert_metrics_daily(db, account_id, camp_id, day2,
                         impressions=500, clicks=25, spend=100, reach=400)

    # New Meta action metrics, split across the two days so the pivot must SUM.
    insert_action_stat(db, account_id, camp_id, day1, "actions", "post_reaction", 10)
    insert_action_stat(db, account_id, camp_id, day2, "actions", "post_reaction", 5)
    insert_action_stat(db, account_id, camp_id, day1,
                       "actions", "onsite_conversion.post_save", 2)
    insert_action_stat(db, account_id, camp_id, day2,
                       "actions", "onsite_conversion.post_save", 4)
    insert_action_stat(db, account_id, camp_id, day1,
                       "action_values", "add_to_cart", 100.50)
    insert_action_stat(db, account_id, camp_id, day2,
                       "action_values", "add_to_cart", 49.50)

    # purchase count (actions/purchase) + revenue (action_values/purchase) so
    # avg_basket_price = conversion_value / purchase is exercised on real data.
    insert_action_stat(db, account_id, camp_id, day1, "actions", "purchase", 3)
    insert_action_stat(db, account_id, camp_id, day2, "actions", "purchase", 1)
    insert_action_stat(db, account_id, camp_id, day1, "action_values", "purchase", 300)
    insert_action_stat(db, account_id, camp_id, day2, "action_values", "purchase", 100)

    db.flush()
    return {"org_id": org_id, "account_id": account_id, "campaign_id": camp_id}


# ── Pivot correctness through get_overview ──────────────────────────────────


def test_overview_pivots_and_sums_new_meta_metrics(db):
    """post_reactions/post_saves/add_to_cart_value are pivoted from
    metric_action_stats and SUMMED across the two days, with correct typing."""
    ctx = _seed_new_meta_metrics(db)
    out = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)
    s = out["summary"]

    # Integer counts summed across day1+day2.
    assert s["post_reactions"] == 15
    assert isinstance(s["post_reactions"], int)
    assert s["post_saves"] == 6
    assert isinstance(s["post_saves"], int)

    # Float value summed (100.50 + 49.50 = 150.00).
    assert s["add_to_cart_value"] == pytest.approx(150.0)
    assert isinstance(s["add_to_cart_value"], float)


def test_overview_new_metrics_isolate_by_action_type(db):
    """The FILTER predicates only sum their own action_type/field_name — an
    unrelated action_type in the same window must NOT leak into the new columns."""
    ctx = _seed_new_meta_metrics(db)
    # Noise: a 'like' (different action_type) and an 'actions'/add_to_cart COUNT
    # (add_to_cart_value must come from field_name='action_values', not 'actions').
    insert_action_stat(db, ctx["account_id"], ctx["campaign_id"], CUR_START,
                       "actions", "like", 999)
    insert_action_stat(db, ctx["account_id"], ctx["campaign_id"], CUR_START,
                       "actions", "add_to_cart", 888)
    db.flush()

    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]
    # Unchanged despite the noise rows.
    assert s["post_reactions"] == 15
    assert s["post_saves"] == 6
    assert s["add_to_cart_value"] == pytest.approx(150.0)


def test_overview_avg_basket_price_from_summed_inputs(db):
    """avg_basket_price = SUM(conversion_value) / SUM(purchase) = 400/4 = 100.0,
    computed after aggregation (not an average of per-day basket prices).

    Per-day basket prices are 300/3=100 and 100/1=100 (equal here), so to make
    the aggregate-vs-avg distinction sharp we assert the exact summed-ratio and
    that it matches conversion_value/purchase from the same summary."""
    ctx = _seed_new_meta_metrics(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]

    assert s["conversion_value"] == pytest.approx(400.0)
    assert s["purchase"] == 4
    assert s["avg_basket_price"] == pytest.approx(100.0)
    # Structural: it equals summed_value / summed_purchase exactly.
    assert s["avg_basket_price"] == pytest.approx(
        s["conversion_value"] / s["purchase"]
    )


def test_overview_avg_basket_price_aggregate_not_avg_of_rows_db(db):
    """DB-level version of the ratio-after-aggregation invariant (P-7).

    Uneven per-day basket prices so avg-of-rows != aggregate:
      day1: revenue=100, purchase=1  → per-day basket 100
      day2: revenue=100, purchase=9  → per-day basket 11.11
    aggregate = 200/10 = 20.0 ; avg-of-rows = 55.56.
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="Uneven")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)
    insert_metrics_daily(db, account_id, camp_id, day1, impressions=10, spend=10)
    insert_metrics_daily(db, account_id, camp_id, day2, impressions=10, spend=10)
    insert_action_stat(db, account_id, camp_id, day1, "actions", "purchase", 1)
    insert_action_stat(db, account_id, camp_id, day2, "actions", "purchase", 9)
    insert_action_stat(db, account_id, camp_id, day1, "action_values", "purchase", 100)
    insert_action_stat(db, account_id, camp_id, day2, "action_values", "purchase", 100)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["purchase"] == 10
    assert s["conversion_value"] == pytest.approx(200.0)
    assert s["avg_basket_price"] == pytest.approx(20.0)
    avg_of_rows = ((100 / 1) + (100 / 9)) / 2  # 55.56
    assert s["avg_basket_price"] != pytest.approx(avg_of_rows)


def test_overview_no_new_metric_rows_yields_null_not_zero(db):
    """A window with base metrics but no post_reaction/post_save/add_to_cart_value
    rows → those keys are null, and avg_basket_price is null (P-1/P-4)."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="BaseOnly")
    insert_metrics_daily(db, account_id, camp_id, CUR_START,
                         impressions=100, clicks=5, spend=20)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["post_reactions"] is None
    assert s["post_saves"] is None
    assert s["add_to_cart_value"] is None
    assert s["avg_basket_price"] is None


# ── Pivot correctness through get_table (per-entity SUM) ─────────────────────


def test_table_pivots_new_metrics_per_entity(db):
    """get_table pivots the same 3 columns per entity, summed over the window,
    and avg_basket_price is derived per row after aggregation."""
    ctx = _seed_new_meta_metrics(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END, level="campaign",
    )
    assert total == 1
    m = rows[0]["metrics"]
    assert m["post_reactions"] == 15
    assert m["post_saves"] == 6
    assert m["add_to_cart_value"] == pytest.approx(150.0)
    # conversion_value comes from the base TABLE_SQL (rev.value) = 400; purchase
    # from the action pivot = 4 → avg_basket_price 100.0.
    assert m["conversion_value"] == pytest.approx(400.0)
    assert m["purchase"] == 4
    assert m["avg_basket_price"] == pytest.approx(100.0)


def test_table_new_metrics_summed_across_entities_independently(db):
    """Two campaigns in the same window: each entity's pivot sums only its own
    action rows (no cross-entity bleed)."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_a = make_campaign(db, account_id, name="A")
    camp_b = make_campaign(db, account_id, name="B")

    insert_metrics_daily(db, account_id, camp_a, CUR_START, impressions=100, spend=10)
    insert_metrics_daily(db, account_id, camp_b, CUR_START, impressions=100, spend=10)
    insert_action_stat(db, account_id, camp_a, CUR_START, "actions", "post_reaction", 7)
    insert_action_stat(db, account_id, camp_b, CUR_START, "actions", "post_reaction", 2)
    insert_action_stat(db, account_id, camp_a, CUR_START,
                       "action_values", "add_to_cart", 12.25)
    db.flush()

    rows, _ = get_table(db, account_id, org_id, CUR_START, CUR_END, level="campaign")
    by_name = {r["name"]: r["metrics"] for r in rows}
    assert by_name["A"]["post_reactions"] == 7
    assert by_name["A"]["add_to_cart_value"] == pytest.approx(12.25)
    assert by_name["B"]["post_reactions"] == 2
    # B has no add_to_cart_value row → null, not A's value.
    assert by_name["B"]["add_to_cart_value"] is None
