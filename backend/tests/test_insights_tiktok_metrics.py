"""Coverage for the TikTok onsite/shop metrics in the insights READ layer.

Gates the change per .claude/rules/test-required-for-done.md — it touches
`metric_action_stats` aggregation, a PRD §11 test-required area, and derives
ratios (roas_shop, cost_per_web_checkout) that MUST be computed after
aggregation (P-7), never as an average of per-row ratios. It also introduces an
AVG-not-SUM metric (avg_watch_time_per_user) that must NEVER be summed across
rows (P-4: reach-style non-additive metric).

What changed in app/services/insights.py:
  1. `_ACTION_PIVOT_COLS` gained TikTok onsite/shop FILTER columns pivoted out
     of metric_action_stats:
       * page_view_onsite       = SUM WHERE field_name='page_events'
                                          AND action_type='page_view'
       * web_add_to_cart_value  = SUM WHERE field_name='page_event_values'
                                          AND action_type='add_to_cart'
       * web_checkout_value     = SUM WHERE field_name='page_event_values'
                                          AND action_type='checkout'
       * avg_watch_time_per_user = AVG WHERE field_name='average_video_play_per_user'
                                          (AVG — never summed)
  2. page_view_onsite is an int key (_ACTION_INT_KEYS); web_add_to_cart_value,
     web_checkout_value, avg_watch_time_per_user are float keys
     (_ACTION_FLOAT_KEYS).
  3. `_finalize_metrics` derives (after aggregation, never stored):
       * roas_shop             = round(web_purchase_value / spend, 4)
       * cost_per_web_checkout = round(spend / web_checkout, 4)
     (web_purchase_value = page_event_values/purchase, web_checkout =
     page_events/checkout — both pre-existing SUM pivot columns.)

Two layers of tests (mirrors test_insights_meta_metrics.py /
test_insights_cpas_metrics.py):
  * Pure-Python unit tests for `_finalize_metrics` and `_action_dict` — no DB,
    always run here.
  * DB-backed pivot tests exercising the real Postgres FILTER/SUM/AVG path
    through `get_overview` / `get_table`. These need a live Postgres 16 (the
    `db` fixture); where no DB host is reachable they error at fixture setup
    rather than run.
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


# ── _finalize_metrics: roas_shop ────────────────────────────────────────────


def test_roas_shop_web_purchase_value_over_spend():
    """web_purchase_value=300, spend=100 → roas_shop=3.0."""
    m = _finalize_metrics({"spend": 100, "web_purchase_value": 300})
    assert m["roas_shop"] == 3.0


def test_roas_shop_rounds_to_four_decimals():
    """roas_shop uses the 4dp rounding convention (like ROAS/CPA)."""
    # value/spend = 100/3 = 33.3333...
    m = _finalize_metrics({"spend": 3, "web_purchase_value": 100})
    assert m["roas_shop"] == pytest.approx(33.3333)


def test_roas_shop_zero_or_none_spend_is_none():
    """spend=0 or None → roas_shop None (denominator guard, P-4)."""
    for spend in (None, 0):
        m = _finalize_metrics({"spend": spend, "web_purchase_value": 300})
        assert m["roas_shop"] is None


def test_roas_shop_none_value_is_none():
    """web_purchase_value missing/None → roas_shop None (numerator guard)."""
    m = _finalize_metrics({"spend": 100, "web_purchase_value": None})
    assert m["roas_shop"] is None
    m2 = _finalize_metrics({"spend": 100})
    assert m2["roas_shop"] is None


# ── _finalize_metrics: cost_per_web_checkout ─────────────────────────────────


def test_cost_per_web_checkout_spend_over_checkout():
    """spend=100, web_checkout=4 → cost_per_web_checkout=25.0."""
    m = _finalize_metrics({"spend": 100, "web_checkout": 4})
    assert m["cost_per_web_checkout"] == 25.0


def test_cost_per_web_checkout_rounds_to_four_decimals():
    """spend/web_checkout = 100/3 = 33.3333... → 33.3333."""
    m = _finalize_metrics({"spend": 100, "web_checkout": 3})
    assert m["cost_per_web_checkout"] == pytest.approx(33.3333)


def test_cost_per_web_checkout_zero_denominator_is_none():
    """web_checkout=0 → None (no divide-by-zero, no fake number, P-4)."""
    m = _finalize_metrics({"spend": 100, "web_checkout": 0})
    assert m["cost_per_web_checkout"] is None


def test_cost_per_web_checkout_none_denominator_is_none():
    """web_checkout missing/None → None."""
    m = _finalize_metrics({"spend": 100, "web_checkout": None})
    assert m["cost_per_web_checkout"] is None
    m2 = _finalize_metrics({"spend": 100})
    assert m2["cost_per_web_checkout"] is None


def test_cost_per_web_checkout_none_or_zero_spend_is_none():
    """spend=0 or None → cost_per_web_checkout None (numerator guard)."""
    for spend in (None, 0):
        m = _finalize_metrics({"spend": spend, "web_checkout": 4})
        assert m["cost_per_web_checkout"] is None


def test_tiktok_derived_keys_present_on_empty_metric_dict():
    """An empty metric dict → both derived keys present and None (honest
    absence, key still emitted so the response envelope is stable, P-1)."""
    m = _finalize_metrics({})
    assert "roas_shop" in m
    assert m["roas_shop"] is None
    assert "cost_per_web_checkout" in m
    assert m["cost_per_web_checkout"] is None


def test_tiktok_ratios_do_not_disturb_neighbouring_derived_metrics():
    """Adding roas_shop/cost_per_web_checkout didn't break the standard
    cost_per_web_purchase / cost_per_web_add_to_cart derived on the same dict."""
    m = _finalize_metrics(
        {
            "spend": 100,
            "web_purchases": 5,       # cost_per_web_purchase = 100/5 = 20.0
            "web_add_to_cart": 4,     # cost_per_web_add_to_cart = 100/4 = 25.0
            "web_purchase_value": 300,
            "web_checkout": 4,
        }
    )
    # Pre-existing (non-TikTok-shop) derived paths unchanged.
    assert m["cost_per_web_purchase"] == 20.0
    assert m["cost_per_web_add_to_cart"] == 25.0
    # New TikTok shop paths.
    assert m["roas_shop"] == 3.0
    assert m["cost_per_web_checkout"] == 25.0


# ── Ratio-after-aggregation invariant (P-7 / PRD §11) ────────────────────────


def test_roas_shop_is_ratio_after_aggregation_not_avg_of_rows():
    """roas_shop must be SUM(web_purchase_value) ÷ SUM(spend) across rows, NOT
    the average of per-row ROAS.

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
        {"spend": summed_spend, "web_purchase_value": summed_value}
    )
    assert m["roas_shop"] == 2.0
    avg_of_rows = ((100 / 10) + (100 / 90)) / 2  # 5.5556
    assert m["roas_shop"] != pytest.approx(avg_of_rows)


def test_cost_per_web_checkout_is_ratio_after_aggregation_not_avg_of_rows():
    """cost_per_web_checkout must be SUM(spend) ÷ SUM(web_checkout), NOT the
    average of per-row cost-per-checkout.

    Two days with uneven spend/checkouts:
      day1: spend=100, checkout=1   → per-row 100.0
      day2: spend=100, checkout=9   → per-row 11.1111
    avg-of-rows would be (100.0 + 11.1111)/2 = 55.5556.
    Correct aggregate = sum(spend)/sum(checkout) = 200/10 = 20.0.
    """
    summed_spend = 100 + 100
    summed_checkout = 1 + 9
    m = _finalize_metrics(
        {"spend": summed_spend, "web_checkout": summed_checkout}
    )
    assert m["cost_per_web_checkout"] == 20.0
    avg_of_rows = ((100 / 1) + (100 / 9)) / 2  # 55.5556
    assert m["cost_per_web_checkout"] != pytest.approx(avg_of_rows)


# ── _action_dict + key-registration typing ──────────────────────────────────


def test_tiktok_action_keys_registered_with_correct_typing():
    """page_view_onsite is an integer key; web_add_to_cart_value,
    web_checkout_value, avg_watch_time_per_user are float keys."""
    assert "page_view_onsite" in _ACTION_INT_KEYS
    assert "web_add_to_cart_value" in _ACTION_FLOAT_KEYS
    assert "web_checkout_value" in _ACTION_FLOAT_KEYS
    assert "avg_watch_time_per_user" in _ACTION_FLOAT_KEYS
    # And not cross-registered (value/avg metrics never coerced to int, the
    # page_view count never coerced to float).
    assert "page_view_onsite" not in _ACTION_FLOAT_KEYS
    assert "web_add_to_cart_value" not in _ACTION_INT_KEYS
    assert "web_checkout_value" not in _ACTION_INT_KEYS
    assert "avg_watch_time_per_user" not in _ACTION_INT_KEYS


def test_action_dict_coerces_tiktok_metrics_to_right_python_type():
    """A pivot row (Numeric values → Decimal) becomes int for the page-view
    count and float for the values / avg watch time.

    metric_action_stats.value is Numeric(18,4), so the pivot SUM/AVG comes back
    as a Decimal-like; _action_dict must coerce page_view_onsite to int and the
    value/avg columns to float."""
    row = {
        "page_view_onsite": Decimal("120"),
        "web_add_to_cart_value": Decimal("456.7800"),
        "web_checkout_value": Decimal("789.1200"),
        "avg_watch_time_per_user": Decimal("12.5000"),
    }
    out = _action_dict(row)

    assert out["page_view_onsite"] == 120
    assert isinstance(out["page_view_onsite"], int)

    assert out["web_add_to_cart_value"] == pytest.approx(456.78)
    assert isinstance(out["web_add_to_cart_value"], float)
    assert out["web_checkout_value"] == pytest.approx(789.12)
    assert isinstance(out["web_checkout_value"], float)
    assert out["avg_watch_time_per_user"] == pytest.approx(12.5)
    assert isinstance(out["avg_watch_time_per_user"], float)


def test_action_dict_missing_tiktok_metrics_are_none():
    """A row with no onsite/shop rows → None, not 0 (honest absence, P-1/P-4)."""
    out = _action_dict({"clicks": 5})  # unrelated key only
    assert out["page_view_onsite"] is None
    assert out["web_add_to_cart_value"] is None
    assert out["web_checkout_value"] is None
    assert out["avg_watch_time_per_user"] is None


# ── TikTok engagement / live SUMmable counts (raw counts, no derived ratio) ───
#
# Four SUM pivot columns added to _ACTION_PIVOT_COLS, all integer counts:
#   engagements          → total_engagement
#   ix_product_click_count → product_clicks_ix
#   live_effective_views → live_views_10s
#   live_product_clicks  → live_product_clicks
# Distinguished ONLY by field_name in the pivot. Critically, product_clicks_ix
# (ix_product_click_count) and live_product_clicks share NOTHING but must not be
# confused; and both are counts pivoted with SUM. No derived ratio is emitted
# for any of them — they stay raw counts.


def test_tiktok_engagement_live_keys_registered_as_int():
    """All 4 new counts are integer keys (SUMmable counts), never float."""
    for k in ("total_engagement", "product_clicks_ix", "live_views_10s",
              "live_product_clicks"):
        assert k in _ACTION_INT_KEYS, f"{k} not registered as int key"
        assert k not in _ACTION_FLOAT_KEYS, f"{k} wrongly registered as float"


def test_action_dict_coerces_tiktok_engagement_live_to_int():
    """Numeric pivot values (Decimal) coerce to int for the 4 counts."""
    row = {
        "total_engagement": Decimal("1234"),
        "product_clicks_ix": Decimal("56"),
        "live_views_10s": Decimal("789"),
        "live_product_clicks": Decimal("12"),
    }
    out = _action_dict(row)

    assert out["total_engagement"] == 1234
    assert isinstance(out["total_engagement"], int)
    assert out["product_clicks_ix"] == 56
    assert isinstance(out["product_clicks_ix"], int)
    assert out["live_views_10s"] == 789
    assert isinstance(out["live_views_10s"], int)
    assert out["live_product_clicks"] == 12
    assert isinstance(out["live_product_clicks"], int)


def test_action_dict_missing_tiktok_engagement_live_are_none():
    """Absent counts → None, not 0 (honest absence, P-1/P-4)."""
    out = _action_dict({"clicks": 5})
    assert out["total_engagement"] is None
    assert out["product_clicks_ix"] is None
    assert out["live_views_10s"] is None
    assert out["live_product_clicks"] is None


def test_tiktok_engagement_live_counts_no_derived_ratio():
    """These are RAW counts — _finalize_metrics must NOT invent a derived ratio
    keyed off them (no `*_rate`/`cost_per_*` for the 4 counts)."""
    m = _finalize_metrics(
        {
            "spend": 100,
            "total_engagement": 200,
            "product_clicks_ix": 10,
            "live_views_10s": 50,
            "live_product_clicks": 5,
        }
    )
    # No derived key derived from any of the 4 raw counts.
    for forbidden in (
        "engagement_rate_shop", "cost_per_engagement", "product_click_rate_ix",
        "cost_per_product_click_ix", "live_view_rate", "cost_per_live_view",
        "live_product_click_rate", "cost_per_live_product_click",
    ):
        assert forbidden not in m, f"unexpected derived key {forbidden}"
    # Raw counts pass through untouched.
    assert m["total_engagement"] == 200
    assert m["product_clicks_ix"] == 10
    assert m["live_views_10s"] == 50
    assert m["live_product_clicks"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed pivot tests — require a live Postgres 16 (the `db` fixture).
# ─────────────────────────────────────────────────────────────────────────────

# A 7-day current window (mirrors the existing meta-metrics / cpas suites so the
# seeding pattern is identical).
CUR_START = date(2026, 6, 8)
CUR_END = date(2026, 6, 14)
PRIOR_START, PRIOR_END = resolve_prior_period(CUR_START, CUR_END)


def _seed_tiktok_metrics(db):
    """One org/account/campaign with TikTok onsite/shop action + value rows
    across TWO days in the current window, plus base spend so the derived
    ratios are exercised end-to-end from summed inputs.

    Current window (2 days):
      day1 (Jun 8): page_view=80, add_to_cart_value=100.50, checkout=3,
                    checkout_value=200, web_purchase_value=200, spend=200,
                    average_video_play_per_user=10
      day2 (Jun 9): page_view=40, add_to_cart_value=49.50, checkout=1,
                    checkout_value=100, web_purchase_value=100, spend=100,
                    average_video_play_per_user=20
    Sums: page_view_onsite=120, web_add_to_cart_value=150.00, web_checkout=4,
          web_checkout_value=300, web_purchase_value=300, spend=300
    AVG:  avg_watch_time_per_user = (10 + 20)/2 = 15.0 (NOT 30 — never summed)
    Derived: roas_shop = web_purchase_value/spend = 300/300 = 1.0
             cost_per_web_checkout = spend/web_checkout = 300/4 = 75.0
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="TikTokAlpha")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)

    insert_metrics_daily(db, account_id, camp_id, day1,
                         impressions=1000, clicks=50, spend=200, reach=800)
    insert_metrics_daily(db, account_id, camp_id, day2,
                         impressions=500, clicks=25, spend=100, reach=400)

    # page_events (onsite page views + checkouts) split across the two days.
    insert_action_stat(db, account_id, camp_id, day1, "page_events", "page_view", 80)
    insert_action_stat(db, account_id, camp_id, day2, "page_events", "page_view", 40)
    insert_action_stat(db, account_id, camp_id, day1, "page_events", "checkout", 3)
    insert_action_stat(db, account_id, camp_id, day2, "page_events", "checkout", 1)
    # page_events/purchase → web_purchase_value's SIBLING count (unused here);
    # the ROAS numerator comes from page_event_values/purchase below.
    insert_action_stat(db, account_id, camp_id, day1, "page_event_values", "purchase", 200)
    insert_action_stat(db, account_id, camp_id, day2, "page_event_values", "purchase", 100)

    # page_event_values (onsite values).
    insert_action_stat(db, account_id, camp_id, day1,
                       "page_event_values", "add_to_cart", 100.50)
    insert_action_stat(db, account_id, camp_id, day2,
                       "page_event_values", "add_to_cart", 49.50)
    insert_action_stat(db, account_id, camp_id, day1,
                       "page_event_values", "checkout", 200)
    insert_action_stat(db, account_id, camp_id, day2,
                       "page_event_values", "checkout", 100)

    # average_video_play_per_user — pivoted with AVG, never summed.
    insert_action_stat(db, account_id, camp_id, day1,
                       "average_video_play_per_user", "video_play", 10)
    insert_action_stat(db, account_id, camp_id, day2,
                       "average_video_play_per_user", "video_play", 20)

    db.flush()
    return {"org_id": org_id, "account_id": account_id, "campaign_id": camp_id}


# ── Pivot correctness through get_overview ──────────────────────────────────


def test_overview_pivots_and_sums_tiktok_metrics(db):
    """page_view_onsite / web_add_to_cart_value / web_checkout_value are pivoted
    from metric_action_stats and SUMMED across the two days, with correct
    typing (int count, float values)."""
    ctx = _seed_tiktok_metrics(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]

    assert s["page_view_onsite"] == 120
    assert isinstance(s["page_view_onsite"], int)

    assert s["web_add_to_cart_value"] == pytest.approx(150.0)
    assert isinstance(s["web_add_to_cart_value"], float)
    assert s["web_checkout_value"] == pytest.approx(300.0)
    assert isinstance(s["web_checkout_value"], float)


def test_overview_avg_watch_time_per_user_is_avg_not_sum(db):
    """P-4 invariant: avg_watch_time_per_user is a NON-ADDITIVE metric pivoted
    with AVG, never summed across rows.

    day1=10, day2=20 → AVG=15.0, NOT SUM=30. This pins the AVG(...) FILTER path
    (a SUM here would be the exact reach-style bug this test class guards)."""
    ctx = _seed_tiktok_metrics(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]

    assert s["avg_watch_time_per_user"] == pytest.approx(15.0)
    # Explicitly NOT the sum (which would be 30) — the whole point of P-4 here.
    assert s["avg_watch_time_per_user"] != pytest.approx(30.0)
    assert isinstance(s["avg_watch_time_per_user"], float)


def test_overview_avg_watch_time_per_user_uneven_case(db):
    """Pin a case where sum != avg with uneven per-day values so an accidental
    SUM would produce a distinctly wrong number.

      day1=5, day2=100  → AVG=52.5, SUM=105.
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="WatchTime")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)
    insert_metrics_daily(db, account_id, camp_id, day1, impressions=10, spend=10)
    insert_metrics_daily(db, account_id, camp_id, day2, impressions=10, spend=10)
    insert_action_stat(db, account_id, camp_id, day1,
                       "average_video_play_per_user", "video_play", 5)
    insert_action_stat(db, account_id, camp_id, day2,
                       "average_video_play_per_user", "video_play", 100)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["avg_watch_time_per_user"] == pytest.approx(52.5)
    assert s["avg_watch_time_per_user"] != pytest.approx(105.0)


def test_overview_tiktok_derived_ratios_from_summed_inputs(db):
    """roas_shop and cost_per_web_checkout derived after aggregation:
      roas_shop             = web_purchase_value/spend = 300/300 = 1.0
      cost_per_web_checkout = spend/web_checkout       = 300/4   = 75.0
    """
    ctx = _seed_tiktok_metrics(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]

    assert s["spend"] == pytest.approx(300.0)
    assert s["web_purchase_value"] == pytest.approx(300.0)
    assert s["web_checkout"] == 4
    assert s["roas_shop"] == pytest.approx(1.0)
    assert s["cost_per_web_checkout"] == pytest.approx(75.0)
    # Structural: roas_shop equals summed_value / summed_spend exactly.
    assert s["roas_shop"] == pytest.approx(s["web_purchase_value"] / s["spend"])


def test_overview_tiktok_isolate_by_action_type_and_field_name(db):
    """The FILTER predicates only sum their own field_name/action_type. Guards:

      1. page_event_values/add_to_cart must NOT leak into web_checkout_value
         (action_type isolation within page_event_values).
      2. page_event_values/add_to_cart must NOT leak into web_purchase_value
         (which is page_event_values/purchase).
      3. page_events/page_view (a COUNT) must NOT leak into web_add_to_cart_value
         (which comes from page_event_values, a different field_name).
    """
    ctx = _seed_tiktok_metrics(db)
    # Noise: an unrelated page_events action_type mapping to no shop column, plus
    # a page_events/add_to_cart COUNT (the *value* must come from
    # page_event_values, never page_events).
    insert_action_stat(db, ctx["account_id"], ctx["campaign_id"], CUR_START,
                       "page_events", "add_to_cart", 999)
    insert_action_stat(db, ctx["account_id"], ctx["campaign_id"], CUR_START,
                       "page_events", "purchase", 888)
    db.flush()

    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]
    # web_checkout_value comes ONLY from page_event_values/checkout (=300), not
    # from the add_to_cart value column.
    assert s["web_checkout_value"] == pytest.approx(300.0)
    # web_purchase_value comes ONLY from page_event_values/purchase (=300), not
    # from add_to_cart or the page_events/purchase COUNT noise.
    assert s["web_purchase_value"] == pytest.approx(300.0)
    # web_add_to_cart_value comes ONLY from page_event_values (=150), unaffected
    # by the page_events/add_to_cart COUNT.
    assert s["web_add_to_cart_value"] == pytest.approx(150.0)
    # page_view_onsite unchanged by the noise.
    assert s["page_view_onsite"] == 120


def test_overview_tiktok_ratios_aggregate_not_avg_of_rows_db(db):
    """DB-level ratio-after-aggregation invariant (P-7) for roas_shop.

    Uneven per-day spend so avg-of-rows != aggregate:
      day1: value=100, spend=10  → per-day roas 10.0
      day2: value=100, spend=90  → per-day roas 1.1111
    aggregate = 200/100 = 2.0 ; avg-of-rows = 5.5556.
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="ShopUneven")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)
    insert_metrics_daily(db, account_id, camp_id, day1, impressions=10, spend=10)
    insert_metrics_daily(db, account_id, camp_id, day2, impressions=10, spend=90)
    insert_action_stat(db, account_id, camp_id, day1,
                       "page_event_values", "purchase", 100)
    insert_action_stat(db, account_id, camp_id, day2,
                       "page_event_values", "purchase", 100)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["spend"] == pytest.approx(100.0)
    assert s["web_purchase_value"] == pytest.approx(200.0)
    assert s["roas_shop"] == pytest.approx(2.0)
    avg_of_rows = ((100 / 10) + (100 / 90)) / 2  # 5.5556
    assert s["roas_shop"] != pytest.approx(avg_of_rows)


def test_overview_cost_per_web_checkout_aggregate_not_avg_of_rows_db(db):
    """DB-level ratio-after-aggregation invariant (P-7) for cost_per_web_checkout.

    Uneven per-day checkouts:
      day1: spend=100, checkout=1  → per-day 100.0
      day2: spend=100, checkout=9  → per-day 11.1111
    aggregate = 200/10 = 20.0 ; avg-of-rows = 55.5556.
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="CheckoutUneven")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)
    insert_metrics_daily(db, account_id, camp_id, day1, impressions=10, spend=100)
    insert_metrics_daily(db, account_id, camp_id, day2, impressions=10, spend=100)
    insert_action_stat(db, account_id, camp_id, day1, "page_events", "checkout", 1)
    insert_action_stat(db, account_id, camp_id, day2, "page_events", "checkout", 9)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["spend"] == pytest.approx(200.0)
    assert s["web_checkout"] == 10
    assert s["cost_per_web_checkout"] == pytest.approx(20.0)
    avg_of_rows = ((100 / 1) + (100 / 9)) / 2  # 55.5556
    assert s["cost_per_web_checkout"] != pytest.approx(avg_of_rows)


def test_overview_no_tiktok_rows_yields_null_not_zero(db):
    """A window with base metrics but no onsite/shop rows → every TikTok key is
    null and every derived TikTok ratio is null (P-1/P-4)."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="TikTokBaseOnly")
    insert_metrics_daily(db, account_id, camp_id, CUR_START,
                         impressions=100, clicks=5, spend=20)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["page_view_onsite"] is None
    assert s["web_add_to_cart_value"] is None
    assert s["web_checkout_value"] is None
    assert s["avg_watch_time_per_user"] is None
    assert s["roas_shop"] is None
    assert s["cost_per_web_checkout"] is None


# ── Pivot correctness through get_table (per-entity SUM / AVG) ────────────────


def test_table_pivots_tiktok_metrics_per_entity(db):
    """get_table pivots the same TikTok columns per entity — SUM for the counts
    and values, AVG for avg_watch_time_per_user — and derives the TikTok ratios
    per row after aggregation."""
    ctx = _seed_tiktok_metrics(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END, level="campaign",
    )
    assert total == 1
    m = rows[0]["metrics"]
    assert m["page_view_onsite"] == 120
    assert m["web_add_to_cart_value"] == pytest.approx(150.0)
    assert m["web_checkout_value"] == pytest.approx(300.0)
    # AVG not SUM at entity grain too.
    assert m["avg_watch_time_per_user"] == pytest.approx(15.0)
    assert m["avg_watch_time_per_user"] != pytest.approx(30.0)
    # Derived after aggregation.
    assert m["roas_shop"] == pytest.approx(1.0)
    assert m["cost_per_web_checkout"] == pytest.approx(75.0)


def test_table_tiktok_summed_across_entities_independently(db):
    """Two campaigns in the same window: each entity's pivot sums/averages only
    its own onsite/shop rows (no cross-entity bleed)."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_a = make_campaign(db, account_id, name="A")
    camp_b = make_campaign(db, account_id, name="B")

    insert_metrics_daily(db, account_id, camp_a, CUR_START, impressions=100, spend=10)
    insert_metrics_daily(db, account_id, camp_b, CUR_START, impressions=100, spend=10)
    insert_action_stat(db, account_id, camp_a, CUR_START, "page_events", "page_view", 7)
    insert_action_stat(db, account_id, camp_b, CUR_START, "page_events", "page_view", 2)
    insert_action_stat(db, account_id, camp_a, CUR_START,
                       "page_event_values", "checkout", 12.25)
    insert_action_stat(db, account_id, camp_a, CUR_START,
                       "average_video_play_per_user", "video_play", 8)
    db.flush()

    rows, _ = get_table(db, account_id, org_id, CUR_START, CUR_END, level="campaign")
    by_name = {r["name"]: r["metrics"] for r in rows}
    assert by_name["A"]["page_view_onsite"] == 7
    assert by_name["A"]["web_checkout_value"] == pytest.approx(12.25)
    assert by_name["A"]["avg_watch_time_per_user"] == pytest.approx(8.0)
    assert by_name["B"]["page_view_onsite"] == 2
    # B has no checkout-value / watch-time row → null, not A's value.
    assert by_name["B"]["web_checkout_value"] is None
    assert by_name["B"]["avg_watch_time_per_user"] is None


# ── TikTok engagement / live SUMmable counts through the real pivot ──────────


def _seed_tiktok_engagement_live(db):
    """One org/account/campaign with the 4 new count field_names across TWO days.

    day1 (Jun 8): engagements=100, ix_product_click_count=10,
                  live_effective_views=40, live_product_clicks=3
    day2 (Jun 9): engagements=50,  ix_product_click_count=5,
                  live_effective_views=20, live_product_clicks=2
    Sums: total_engagement=150, product_clicks_ix=15, live_views_10s=60,
          live_product_clicks=5
    """
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="TikTokEngageLive")

    day1 = CUR_START
    day2 = CUR_START.replace(day=9)

    insert_metrics_daily(db, account_id, camp_id, day1, impressions=1000, spend=100)
    insert_metrics_daily(db, account_id, camp_id, day2, impressions=500, spend=50)

    insert_action_stat(db, account_id, camp_id, day1, "engagements", "engagement", 100)
    insert_action_stat(db, account_id, camp_id, day2, "engagements", "engagement", 50)
    # ix_product_click_count and live_product_clicks BOTH carry action_type
    # 'product_click' — they are distinguished ONLY by field_name.
    insert_action_stat(db, account_id, camp_id, day1,
                       "ix_product_click_count", "product_click", 10)
    insert_action_stat(db, account_id, camp_id, day2,
                       "ix_product_click_count", "product_click", 5)
    insert_action_stat(db, account_id, camp_id, day1,
                       "live_effective_views", "view", 40)
    insert_action_stat(db, account_id, camp_id, day2,
                       "live_effective_views", "view", 20)
    insert_action_stat(db, account_id, camp_id, day1,
                       "live_product_clicks", "product_click", 3)
    insert_action_stat(db, account_id, camp_id, day2,
                       "live_product_clicks", "product_click", 2)

    db.flush()
    return {"org_id": org_id, "account_id": account_id, "campaign_id": camp_id}


def test_overview_pivots_and_sums_tiktok_engagement_live(db):
    """All 4 counts are pivoted from metric_action_stats and SUMMED across the
    two days, with integer typing."""
    ctx = _seed_tiktok_engagement_live(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]

    assert s["total_engagement"] == 150
    assert isinstance(s["total_engagement"], int)
    assert s["product_clicks_ix"] == 15
    assert isinstance(s["product_clicks_ix"], int)
    assert s["live_views_10s"] == 60
    assert isinstance(s["live_views_10s"], int)
    assert s["live_product_clicks"] == 5
    assert isinstance(s["live_product_clicks"], int)


def test_overview_ix_and_live_product_clicks_do_not_bleed(db):
    """CRITICAL field_name isolation: ix_product_click_count (→product_clicks_ix)
    and live_product_clicks share action_type 'product_click' and must NOT be
    summed together. The pivot distinguishes them by field_name only.

    Seed asymmetric values so a bleed produces a distinctly wrong number:
      product_clicks_ix   = 10 + 5 = 15
      live_product_clicks = 3 + 2 = 5
    A field_name-blind pivot (summing on action_type alone) would give 20 for
    both — this pins that neither equals the other's value nor the combined 20.
    """
    ctx = _seed_tiktok_engagement_live(db)
    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]

    assert s["product_clicks_ix"] == 15  # ONLY ix_product_click_count rows
    assert s["live_product_clicks"] == 5  # ONLY live_product_clicks rows
    # Explicitly not each other and not the bleed-combined total (20).
    assert s["product_clicks_ix"] != s["live_product_clicks"]
    assert s["product_clicks_ix"] != 20
    assert s["live_product_clicks"] != 20


def test_overview_engagements_and_live_views_isolate_by_field_name(db):
    """total_engagement (engagements) and live_views_10s (live_effective_views)
    each sum ONLY their own field_name; unrelated product_click rows don't leak.

    Add a noise engagements/product_click row and a live_effective_views/
    product_click row to prove the field_name FILTER, not action_type, decides.
    """
    ctx = _seed_tiktok_engagement_live(db)
    # Noise that shares action_type with the product-click metrics but a
    # different field_name — must NOT change engagement/live-view totals, and
    # (being engagements/live_effective_views field_names) DOES fold into them.
    insert_action_stat(db, ctx["account_id"], ctx["campaign_id"], CUR_START,
                       "actions", "product_click", 777)  # unrelated field_name
    db.flush()

    s = get_overview(db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END)["summary"]
    assert s["total_engagement"] == 150  # engagements field only
    assert s["live_views_10s"] == 60     # live_effective_views field only
    # The 'actions' noise maps to none of the 4 count columns.
    assert s["product_clicks_ix"] == 15
    assert s["live_product_clicks"] == 5


def test_overview_no_tiktok_engagement_live_rows_yields_null_not_zero(db):
    """Base metrics but no engagement/live rows → every count is null, not 0."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_id = make_campaign(db, account_id, name="EngageLiveBaseOnly")
    insert_metrics_daily(db, account_id, camp_id, CUR_START, impressions=100, spend=20)
    db.flush()

    s = get_overview(db, account_id, org_id, CUR_START, CUR_END)["summary"]
    assert s["total_engagement"] is None
    assert s["product_clicks_ix"] is None
    assert s["live_views_10s"] is None
    assert s["live_product_clicks"] is None


def test_table_pivots_tiktok_engagement_live_per_entity(db):
    """get_table pivots and SUMs the 4 counts per entity."""
    ctx = _seed_tiktok_engagement_live(db)
    rows, total = get_table(
        db, ctx["account_id"], ctx["org_id"], CUR_START, CUR_END, level="campaign",
    )
    assert total == 1
    m = rows[0]["metrics"]
    assert m["total_engagement"] == 150
    assert m["product_clicks_ix"] == 15
    assert m["live_views_10s"] == 60
    assert m["live_product_clicks"] == 5


def test_table_tiktok_engagement_live_per_entity_independent(db):
    """Two campaigns: each entity's pivot sums only its own rows. Also re-pins
    the ix vs live product-click field_name isolation at entity grain."""
    org_id = make_org(db)
    conn_id = make_connection(db, org_id)
    account_id = make_account(db, org_id, conn_id)
    camp_a = make_campaign(db, account_id, name="A")
    camp_b = make_campaign(db, account_id, name="B")

    insert_metrics_daily(db, account_id, camp_a, CUR_START, impressions=100, spend=10)
    insert_metrics_daily(db, account_id, camp_b, CUR_START, impressions=100, spend=10)
    # A: engagements + both product-click field_names (asymmetric).
    insert_action_stat(db, account_id, camp_a, CUR_START, "engagements", "engagement", 30)
    insert_action_stat(db, account_id, camp_a, CUR_START,
                       "ix_product_click_count", "product_click", 9)
    insert_action_stat(db, account_id, camp_a, CUR_START,
                       "live_product_clicks", "product_click", 4)
    # B: only live views.
    insert_action_stat(db, account_id, camp_b, CUR_START,
                       "live_effective_views", "view", 11)
    db.flush()

    rows, _ = get_table(db, account_id, org_id, CUR_START, CUR_END, level="campaign")
    by_name = {r["name"]: r["metrics"] for r in rows}

    assert by_name["A"]["total_engagement"] == 30
    assert by_name["A"]["product_clicks_ix"] == 9
    assert by_name["A"]["live_product_clicks"] == 4  # not bled from ix (9)
    assert by_name["A"]["product_clicks_ix"] != by_name["A"]["live_product_clicks"]
    assert by_name["A"]["live_views_10s"] is None  # A has no live-view row

    assert by_name["B"]["live_views_10s"] == 11
    # B has none of the other three → null, not A's values.
    assert by_name["B"]["total_engagement"] is None
    assert by_name["B"]["product_clicks_ix"] is None
    assert by_name["B"]["live_product_clicks"] is None
