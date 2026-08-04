import calendar
import uuid
from datetime import date, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.relativedelta import relativedelta

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.exceptions import ForbiddenError, NotFoundError
from app.models.platform import Account
from app.schemas.common import calculate_offset
from app.services.accounts import assert_account_belongs_to_org

VALID_SORT_COLUMNS = {
    "spend", "impressions", "clicks", "ctr", "cpm", "cpc", "cpp",
    "reach", "roas", "cpa", "conversions", "conversion_rate", "name", "status",
}


def resolve_date_range(
    date_preset: Optional[str], account_timezone: str = "UTC"
) -> tuple[date, date]:
    try:
        tz = ZoneInfo(account_timezone)
    except (ZoneInfoNotFoundError, Exception):
        tz = ZoneInfo("UTC")

    from datetime import datetime
    import datetime as dt_module
    today = datetime.now(tz).date()

    presets = {
        "today": (today, today),
        "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
        # Rolling presets span N calendar days back through today, inclusive
        # (e.g. on Jun 5, last_30d = May 6 .. Jun 5). Single source for the API
        # layer AND the TikTok breakdown worker (which stores at start_date).
        "last_7d": (today - timedelta(days=7), today),
        "last_14d": (today - timedelta(days=14), today),
        "last_28d": (today - timedelta(days=28), today),
        "last_30d": (today - timedelta(days=30), today),
        "last_90d": (today - timedelta(days=90), today),
        "this_month": (today.replace(day=1), today),
        "last_month": (
            (today.replace(day=1) - timedelta(days=1)).replace(day=1),
            today.replace(day=1) - timedelta(days=1),
        ),
        "this_year": (today.replace(month=1, day=1), today),
        "lifetime": (date(2015, 1, 1), today),
    }
    if date_preset not in presets:
        raise ValueError(f"Unknown date_preset: {date_preset}")
    return presets[date_preset]


def _is_full_calendar_month(start: date, end: date) -> bool:
    """True when [start, end] spans exactly one whole calendar month."""
    last_day = calendar.monthrange(start.year, start.month)[1]
    return (
        start.day == 1
        and start.year == end.year
        and start.month == end.month
        and end.day == last_day
    )


def resolve_prior_period(start: date, end: date) -> tuple[date, date]:
    # Full calendar month → previous calendar month (e.g. May 1–31 → Apr 1–30).
    if _is_full_calendar_month(start, end):
        prior_start = start - relativedelta(months=1)
        last_day = calendar.monthrange(prior_start.year, prior_start.month)[1]
        prior_end = prior_start.replace(day=last_day)
        return prior_start, prior_end
    # Otherwise → equal-length window immediately before (rolling presets, custom spans).
    delta = (end - start).days + 1
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=delta - 1)
    return prior_start, prior_end


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# ─── Extended action-based metrics ──────────────────────────────────────────────
#
# Meta `actions`/video arrays and TikTok engagement/conversion/web-app events all
# land in metric_action_stats as (field_name, action_type, value) rows. Rather than
# bolt a LEFT JOIN per metric onto every query, we pivot them in ONE extra query per
# endpoint and merge by entity/date/period in Python. Wrong-platform columns simply
# come back NULL. Computed rates (conversion_rate, engagement_rate, cost_per_result,
# install_cost, plus Meta's cost_per_inline_post_engagement / estimated_ad_recall_rate)
# are derived in `_finalize_metrics`, never stored — matching the ROAS/CPA rule.

_ACTION_PIVOT_COLS = """
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='add_to_cart')         AS add_to_cart,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='initiate_checkout')   AS initiate_checkout,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='landing_page_view')   AS landing_page_views,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='lead')                AS leads,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='view_content')         AS view_content,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='purchase')             AS purchase,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='search')               AS search,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='complete_registration') AS complete_registration,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='like')                AS likes,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='comment')             AS comments,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='share')               AS shares,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='follow')              AS follows,
    SUM(value) FILTER (WHERE field_name='actions' AND action_type='profile_visit')       AS profile_visits,
    SUM(value) FILTER (WHERE field_name='results' AND action_type='result')              AS result,
    SUM(value) FILTER (WHERE field_name='page_events' AND action_type='purchase')        AS web_purchases,
    SUM(value) FILTER (WHERE field_name='page_event_values' AND action_type='purchase')  AS web_purchase_value,
    SUM(value) FILTER (WHERE field_name='page_events' AND action_type='add_to_cart')     AS web_add_to_cart,
    SUM(value) FILTER (WHERE field_name='page_events' AND action_type='checkout')        AS web_checkout,
    SUM(value) FILTER (WHERE field_name='app_events' AND action_type='install')          AS app_installs,
    SUM(value) FILTER (WHERE field_name='video_play_actions')                            AS video_views,
    SUM(value) FILTER (WHERE field_name='video_p25_watched_actions')                     AS video_p25,
    SUM(value) FILTER (WHERE field_name='video_p50_watched_actions')                     AS video_p50,
    SUM(value) FILTER (WHERE field_name='video_p75_watched_actions')                     AS video_p75,
    SUM(value) FILTER (WHERE field_name='video_p100_watched_actions')                    AS video_p100,
    SUM(value) FILTER (WHERE field_name='video_thruplay_watched_actions')                AS video_thruplays,
    SUM(value) FILTER (WHERE field_name='video_continuous_2_sec_watched_actions')        AS video_2s,
    SUM(value) FILTER (WHERE field_name='video_watched_2s')                              AS video_2s_views,
    SUM(value) FILTER (WHERE field_name='video_watched_6s')                              AS video_6s_views,
    AVG(value) FILTER (WHERE field_name='video_avg_time_watched_actions')                AS video_avg_time,
    AVG(value) FILTER (WHERE field_name='average_video_play')                            AS avg_watch_time
""".strip()

_ACTION_WHERE = (
    "FROM metric_action_stats\n"
    "WHERE account_id = :account_id\n"
    "  AND entity_type = :entity_type\n"
    "  AND date BETWEEN :date_start AND :date_end"
)

# Optional campaign-scope filter shared by the Overview-page queries (cards,
# funnel, trends). When :campaign_ids is NULL the predicate is a no-op; otherwise
# only rows whose entity_id is one of the pre-resolved campaign ids survive. Bare
# `entity_id` variant for metric_action_stats (no table alias in _ACTION_WHERE).
_CAMPAIGN_FILTER_BARE = (
    "\n  AND (CAST(:campaign_ids AS uuid[]) IS NULL"
    " OR entity_id = ANY(CAST(:campaign_ids AS uuid[])))"
)
_ACTION_WHERE_CF = _ACTION_WHERE + _CAMPAIGN_FILTER_BARE

_ACTION_OVERVIEW_SQL = f"SELECT\n{_ACTION_PIVOT_COLS}\n{_ACTION_WHERE_CF}"
_ACTION_BY_DATE_SQL = (
    f"SELECT date_trunc(:increment, date)::date AS period_date,\n{_ACTION_PIVOT_COLS}\n"
    f"{_ACTION_WHERE_CF}\nGROUP BY period_date"
)
# get_table consumer — no campaign filter, stays on the plain WHERE.
_ACTION_BY_ENTITY_SQL = (
    f"SELECT entity_id::text AS entity_id,\n{_ACTION_PIVOT_COLS}\n"
    f"{_ACTION_WHERE}\nGROUP BY entity_id"
)
_ACTION_BY_ENTITY_DATE_SQL = (
    f"SELECT entity_id::text AS entity_id, date_trunc(:increment, date)::date AS period_date,\n"
    f"{_ACTION_PIVOT_COLS}\n{_ACTION_WHERE_CF}\nGROUP BY entity_id, period_date"
)

# Count metrics (integer) vs value/avg metrics (float) returned by the pivot.
_ACTION_INT_KEYS = (
    "add_to_cart", "initiate_checkout", "landing_page_views", "leads",
    "view_content", "purchase", "search", "complete_registration",
    "likes", "comments", "shares", "follows", "profile_visits", "result",
    "web_purchases", "web_add_to_cart", "web_checkout", "app_installs",
    "video_views", "video_p25", "video_p50", "video_p75", "video_p100",
    "video_thruplays", "video_2s", "video_2s_views", "video_6s_views",
)
_ACTION_FLOAT_KEYS = ("web_purchase_value", "video_avg_time", "avg_watch_time")


def _action_dict(r) -> dict:
    if not r:
        return {}
    out = {k: _safe_int(r.get(k)) for k in _ACTION_INT_KEYS}
    out.update({k: _safe_float(r.get(k)) for k in _ACTION_FLOAT_KEYS})
    return out


def _finalize_metrics(m: dict) -> dict:
    """Derive computed rates from already-merged base + action values (in place)."""
    spend = m.get("spend")
    clicks = m.get("clicks")
    impr = m.get("impressions")
    reach = m.get("reach")
    conv = m.get("conversions")
    eng = (m.get("likes") or 0) + (m.get("comments") or 0) + (m.get("shares") or 0)
    result = m.get("result")
    installs = m.get("app_installs")
    ipe = m.get("inline_post_engagement")
    recallers = m.get("estimated_ad_recallers")

    m["conversion_rate"] = round(conv / clicks * 100, 4) if conv and clicks else None
    m["engagement_rate"] = round(eng / impr * 100, 4) if eng and impr else None
    m["cost_per_result"] = round(spend / result, 4) if spend and result else None
    m["install_cost"] = round(spend / installs, 4) if spend and installs else None
    m["cost_per_inline_post_engagement"] = round(spend / ipe, 4) if spend and ipe else None
    m["estimated_ad_recall_rate"] = round(recallers / reach * 100, 4) if recallers and reach else None

    # Cost per funnel step (spend ÷ step count) — computed, never stored.
    def _cps(count):
        return round(spend / count, 4) if spend and count else None
    m["cost_per_view_content"] = _cps(m.get("view_content"))
    m["cost_per_add_to_cart"] = _cps(m.get("add_to_cart"))
    m["cost_per_initiate_checkout"] = _cps(m.get("initiate_checkout"))
    m["cost_per_purchase"] = _cps(m.get("purchase"))
    m["cost_per_landing_page_view"] = _cps(m.get("landing_page_views"))
    m["cost_per_lead"] = _cps(m.get("leads"))
    m["cost_per_web_purchase"] = _cps(m.get("web_purchases"))
    m["cost_per_web_add_to_cart"] = _cps(m.get("web_add_to_cart"))
    return m


def _align_keys(a: dict, b: dict) -> None:
    """Make both dicts expose the union of their keys (in place).

    Raw action-count keys (e.g. add_to_cart, shares, web_purchases) are only
    added by the pivot for a window that actually has action rows, so a period
    with no action data ends up missing keys the other period has. Fill any key
    present in one dict but not the other with None in the dict that lacks it.

    Null-fill only: an existing value (including an already-present None) is
    never touched, and no ratio is recomputed. A null here is honest absence of
    a metric, not a fake zero (P-1 / P-4).
    """
    for k in a.keys() - b.keys():
        b[k] = None
    for k in b.keys() - a.keys():
        a[k] = None


def _fetch_action_metrics(db, sql: str, params: dict, key: Optional[str] = None) -> dict:
    """Run a pivot query; return {row[key]: action_dict} or a single action_dict if key is None."""
    rows = db.execute(text(sql), params).mappings().all()
    if key is None:
        return _action_dict(rows[0]) if rows else {}
    return {r[key]: _action_dict(r) for r in rows}


OVERVIEW_SQL = """
SELECT
    SUM(md.impressions)         AS impressions,
    SUM(md.reach)               AS reach,
    SUM(md.clicks)              AS clicks,
    SUM(md.spend)               AS spend,
    SUM(md.inline_link_clicks)  AS inline_link_clicks,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.clicks)::float / SUM(md.impressions) * 100
        ELSE NULL END           AS ctr,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.spend) / SUM(md.impressions) * 1000
        ELSE NULL END           AS cpm,
    CASE WHEN SUM(md.clicks) > 0
        THEN SUM(md.spend) / SUM(md.clicks)
        ELSE NULL END           AS cpc,
    CASE WHEN SUM(md.reach) > 0
        THEN SUM(md.spend) / SUM(md.reach) * 1000
        ELSE NULL END           AS cpp,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.reach)::float / SUM(md.impressions)
        ELSE NULL END           AS frequency,
    SUM(conv.value)             AS conversions,
    SUM(rev.value)              AS conversion_value,
    CASE WHEN SUM(md.spend) > 0
        THEN SUM(rev.value) / SUM(md.spend)
        ELSE NULL END           AS roas,
    CASE WHEN SUM(conv.value) > 0
        THEN SUM(md.spend) / SUM(conv.value)
        ELSE NULL END           AS cpa,
    SUM(oc.value)               AS outbound_clicks,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(oc.value) / SUM(md.impressions) * 100
        ELSE NULL END           AS outbound_clicks_ctr,
    SUM(md.inline_post_engagement)  AS inline_post_engagement,
    SUM(md.estimated_ad_recallers)  AS estimated_ad_recallers,
    MAX(md.fetched_at)          AS cached_at
FROM metrics_daily md
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id
    AND conv.entity_type = md.entity_type
    AND conv.date = md.date
    AND conv.field_name IN ('actions', 'conversions')
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id
    AND rev.entity_type = md.entity_type
    AND rev.date = md.date
    AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
LEFT JOIN metric_action_stats oc
    ON oc.entity_id = md.entity_id
    AND oc.entity_type = md.entity_type
    AND oc.date = md.date
    AND oc.field_name = 'outbound_clicks'
    AND oc.action_type = 'outbound_click'
WHERE md.account_id = :account_id
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
  AND (CAST(:campaign_ids AS uuid[]) IS NULL
       OR md.entity_id = ANY(CAST(:campaign_ids AS uuid[])))
"""

TOP_CAMPAIGNS_SQL = """
SELECT
    c.id::text          AS id,
    c.name              AS name,
    c.status            AS status,
    SUM(md.spend)       AS spend,
    SUM(md.impressions) AS impressions,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.clicks)::float / SUM(md.impressions) * 100
        ELSE NULL END   AS ctr,
    SUM(conv.value)     AS conversions,
    CASE WHEN SUM(md.spend) > 0
        THEN SUM(rev.value) / SUM(md.spend)
        ELSE NULL END   AS roas,
    SUM(oc.value)       AS outbound_clicks
FROM metrics_daily md
JOIN campaigns c ON c.id = md.entity_id
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id
    AND conv.entity_type = 'campaign'
    AND conv.date = md.date
    AND conv.field_name IN ('actions', 'conversions')
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id
    AND rev.entity_type = 'campaign'
    AND rev.date = md.date
    AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
LEFT JOIN metric_action_stats oc
    ON oc.entity_id = md.entity_id
    AND oc.entity_type = 'campaign'
    AND oc.date = md.date
    AND oc.field_name = 'outbound_clicks'
    AND oc.action_type = 'outbound_click'
WHERE md.account_id = :account_id
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
  AND (CAST(:campaign_ids AS uuid[]) IS NULL
       OR md.entity_id = ANY(CAST(:campaign_ids AS uuid[])))
GROUP BY c.id, c.name
ORDER BY SUM(md.spend) DESC NULLS LAST
LIMIT 5
"""


def _resolve_campaign_ids(
    db: Session,
    account_id: str,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> Optional[list[str]]:
    """Resolve the Overview-page campaign filter to a concrete id list.

    Returns None when no filter is active (SQL predicate becomes a no-op). When a
    filter is active but matches nothing, returns [] so downstream queries yield
    zero rows rather than silently ignoring the filter.
    """
    if not status and not search:
        return None
    sql = "SELECT id::text FROM campaigns WHERE account_id = :account_id"
    p: dict = {"account_id": uuid.UUID(account_id)}
    if status:
        sql += " AND status = :status"
        p["status"] = status
    if search:
        sql += " AND name ILIKE '%' || :search || '%'"
        p["search"] = search
    return [r[0] for r in db.execute(text(sql), p).all()]


def get_overview(
    db: Session,
    account_id: str,
    org_id: str,
    date_start: date,
    date_end: date,
    date_preset: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    assert_account_belongs_to_org(db, account_id, org_id)
    campaign_ids = _resolve_campaign_ids(db, account_id, status, search)
    params = {
        "account_id": uuid.UUID(account_id),
        "date_start": date_start,
        "date_end": date_end,
        "campaign_ids": campaign_ids,
    }

    row = db.execute(text(OVERVIEW_SQL), params).mappings().first()
    prior_start, prior_end = resolve_prior_period(date_start, date_end)
    prior_params = {**params, "date_start": prior_start, "date_end": prior_end}
    prior_row = db.execute(text(OVERVIEW_SQL), prior_params).mappings().first()

    top = db.execute(text(TOP_CAMPAIGNS_SQL), params).mappings().all()

    # Freshness token for the current period: MAX(fetched_at) across the same
    # rows the current-window query aggregates. A re-sync bumps fetched_at, which
    # invalidates the on-demand AI-summary cache keyed on it (P-1). Not a metric,
    # so it's pulled out before the _safe_float coercion below.
    cached_at = row["cached_at"] if row else None

    def row_to_dict(r):
        if not r:
            return {}
        return {k: _safe_float(v) for k, v in r.items() if k != "cached_at"}

    curr = row_to_dict(row)
    prev = row_to_dict(prior_row)

    action = _fetch_action_metrics(
        db, _ACTION_OVERVIEW_SQL, {**params, "entity_type": "campaign"}
    )
    prior_action = _fetch_action_metrics(
        db, _ACTION_OVERVIEW_SQL, {**prior_params, "entity_type": "campaign"}
    )

    def _build_summary(base: dict, act: dict) -> dict:
        s = {
            "spend": base.get("spend"),
            "impressions": _safe_int(base.get("impressions")),
            "reach": _safe_int(base.get("reach")),
            "frequency": base.get("frequency"),
            "clicks": _safe_int(base.get("clicks")),
            "inline_link_clicks": _safe_int(base.get("inline_link_clicks")),
            "ctr": base.get("ctr"),
            "cpm": base.get("cpm"),
            "cpc": base.get("cpc"),
            "cpp": base.get("cpp"),
            "conversions": base.get("conversions"),
            "conversion_value": base.get("conversion_value"),
            "roas": base.get("roas"),
            "cpa": base.get("cpa"),
            "outbound_clicks": base.get("outbound_clicks"),
            "outbound_clicks_ctr": base.get("outbound_clicks_ctr"),
            "inline_post_engagement": _safe_int(base.get("inline_post_engagement")),
            "estimated_ad_recallers": _safe_int(base.get("estimated_ad_recallers")),
        }
        s.update(act)
        _finalize_metrics(s)
        return s

    summary = _build_summary(curr, action)
    previous = _build_summary(prev, prior_action)
    # Guarantee an identical key set across the pair: a window with no action
    # rows would otherwise omit raw action-count keys the other window has.
    _align_keys(summary, previous)

    return {
        "period": {
            "date_start": date_start,
            "date_stop": date_end,
            "preset": date_preset,
        },
        "cached_at": cached_at,
        "summary": summary,
        "previous": previous,
        "vs_previous": {
            "spend": _pct_change(curr.get("spend"), prev.get("spend")),
            "impressions": _pct_change(curr.get("impressions"), prev.get("impressions")),
            "clicks": _pct_change(curr.get("clicks"), prev.get("clicks")),
            "ctr": _pct_change(curr.get("ctr"), prev.get("ctr")),
            "cpm": _pct_change(curr.get("cpm"), prev.get("cpm")),
            "conversions": _pct_change(curr.get("conversions"), prev.get("conversions")),
            "roas": _pct_change(curr.get("roas"), prev.get("roas")),
            "outbound_clicks": _pct_change(curr.get("outbound_clicks"), prev.get("outbound_clicks")),
            "outbound_clicks_ctr": _pct_change(curr.get("outbound_clicks_ctr"), prev.get("outbound_clicks_ctr")),
        },
        "top_campaigns": [
            {
                "id": r["id"],
                "name": r["name"],
                "status": r["status"],
                "spend": _safe_float(r["spend"]),
                "impressions": _safe_int(r["impressions"]),
                "ctr": _safe_float(r["ctr"]),
                "conversions": _safe_float(r["conversions"]),
                "roas": _safe_float(r["roas"]),
                "outbound_clicks": _safe_float(r["outbound_clicks"]),
            }
            for r in top
        ],
    }


TIMESERIES_SQL = """
SELECT
    date_trunc(:increment, md.date)::date   AS period_date,
    SUM(md.impressions)                     AS impressions,
    SUM(md.reach)                           AS reach,
    SUM(md.clicks)                          AS clicks,
    SUM(md.spend)                           AS spend,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.clicks)::float / SUM(md.impressions) * 100
        ELSE NULL END                       AS ctr,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.spend) / SUM(md.impressions) * 1000
        ELSE NULL END                       AS cpm,
    CASE WHEN SUM(md.clicks) > 0
        THEN SUM(md.spend) / SUM(md.clicks)
        ELSE NULL END                       AS cpc,
    SUM(conv.value)                         AS conversions,
    CASE WHEN SUM(md.spend) > 0
        THEN SUM(rev.value) / SUM(md.spend)
        ELSE NULL END                       AS roas,
    SUM(oc.value)                           AS outbound_clicks,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(oc.value) / SUM(md.impressions) * 100
        ELSE NULL END                       AS outbound_clicks_ctr,
    SUM(md.inline_post_engagement)          AS inline_post_engagement,
    SUM(md.estimated_ad_recallers)          AS estimated_ad_recallers
FROM metrics_daily md
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id AND conv.entity_type = md.entity_type
    AND conv.date = md.date AND conv.field_name IN ('actions', 'conversions')
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id AND rev.entity_type = md.entity_type
    AND rev.date = md.date AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
LEFT JOIN metric_action_stats oc
    ON oc.entity_id = md.entity_id AND oc.entity_type = md.entity_type
    AND oc.date = md.date AND oc.field_name = 'outbound_clicks'
    AND oc.action_type = 'outbound_click'
WHERE md.account_id = :account_id
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
  AND (CAST(:campaign_ids AS uuid[]) IS NULL
       OR md.entity_id = ANY(CAST(:campaign_ids AS uuid[])))
GROUP BY period_date
ORDER BY period_date
"""

TIMESERIES_BY_ENTITY_SQL = """
SELECT
    md.entity_id::text                      AS entity_id,
    ename.name                              AS entity_name,
    date_trunc(:increment, md.date)::date   AS period_date,
    SUM(md.spend)                           AS spend,
    SUM(md.impressions)                     AS impressions,
    SUM(md.clicks)                          AS clicks,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.clicks)::float / SUM(md.impressions) * 100
        ELSE NULL END                       AS ctr,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.spend) / SUM(md.impressions) * 1000
        ELSE NULL END                       AS cpm,
    CASE WHEN SUM(md.clicks) > 0
        THEN SUM(md.spend) / SUM(md.clicks)
        ELSE NULL END                       AS cpc,
    SUM(conv.value)                         AS conversions,
    CASE WHEN SUM(md.spend) > 0
        THEN SUM(rev.value) / SUM(md.spend)
        ELSE NULL END                       AS roas
FROM metrics_daily md
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id AND conv.entity_type = md.entity_type
    AND conv.date = md.date AND conv.field_name IN ('actions', 'conversions')
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id AND rev.entity_type = md.entity_type
    AND rev.date = md.date AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
LEFT JOIN (
    SELECT id::text AS id, name FROM campaigns
    UNION ALL
    SELECT id::text AS id, name FROM ad_groups
    UNION ALL
    SELECT id::text AS id, name FROM ads
) ename ON ename.id = md.entity_id::text
WHERE md.account_id = :account_id
  AND md.entity_type = :entity_type
  AND md.date BETWEEN :date_start AND :date_end
  AND (CAST(:campaign_ids AS uuid[]) IS NULL
       OR md.entity_id = ANY(CAST(:campaign_ids AS uuid[])))
GROUP BY md.entity_id, entity_name, period_date
ORDER BY SUM(md.spend) DESC NULLS LAST, md.entity_id, period_date
"""


def get_timeseries(
    db: Session,
    account_id: str,
    org_id: str,
    date_start: date,
    date_end: date,
    metrics: list[str],
    level: str = "account",
    time_increment: str = "day",
    compare_previous: bool = False,
    date_preset: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    assert_account_belongs_to_org(db, account_id, org_id)
    increment_map = {"day": "day", "week": "week", "month": "month"}
    pg_increment = increment_map.get(time_increment, "day")

    campaign_ids = _resolve_campaign_ids(db, account_id, status, search)
    params = {
        "account_id": uuid.UUID(account_id),
        "date_start": date_start,
        "date_end": date_end,
        "increment": pg_increment,
        "campaign_ids": campaign_ids,
    }
    rows = db.execute(text(TIMESERIES_SQL), params).mappings().all()
    action_by_date = _fetch_action_metrics(
        db, _ACTION_BY_DATE_SQL, {**params, "entity_type": "campaign"}, key="period_date"
    )

    def row_to_point(r):
        p = {
            "date": r["period_date"],
            "spend": _safe_float(r.get("spend")),
            "impressions": _safe_int(r.get("impressions")),
            "clicks": _safe_int(r.get("clicks")),
            "ctr": _safe_float(r.get("ctr")),
            "cpm": _safe_float(r.get("cpm")),
            "cpc": _safe_float(r.get("cpc")),
            "reach": _safe_int(r.get("reach")),
            "conversions": _safe_float(r.get("conversions")),
            "roas": _safe_float(r.get("roas")),
            "outbound_clicks": _safe_float(r.get("outbound_clicks")),
            "outbound_clicks_ctr": _safe_float(r.get("outbound_clicks_ctr")),
            "inline_post_engagement": _safe_int(r.get("inline_post_engagement")),
            "estimated_ad_recallers": _safe_int(r.get("estimated_ad_recallers")),
        }
        p.update(action_by_date.get(r["period_date"], {}))
        return _finalize_metrics(p)

    series = [row_to_point(r) for r in rows]
    previous_series = None
    series_by_entity = None

    prior_start = prior_end = None
    if compare_previous:
        prior_start, prior_end = resolve_prior_period(date_start, date_end)
        prior_params = {**params, "date_start": prior_start, "date_end": prior_end}
        prior_rows = db.execute(text(TIMESERIES_SQL), prior_params).mappings().all()
        previous_series = [row_to_point(r) for r in prior_rows]

    if level != "account":
        entity_type_map = {"campaign": "campaign", "adgroup": "adgroup", "ad": "ad"}
        entity_type = entity_type_map.get(level, "campaign")

        # The campaign filter is expressed as campaign ids, so it only lines up
        # with entity_id when the breakdown itself is at campaign grain. For
        # adgroup/ad breakdowns drop it (else every id mismatches → zero rows).
        entity_params = {
            **params,
            "entity_type": entity_type,
            "campaign_ids": campaign_ids if entity_type == "campaign" else None,
        }
        entity_rows = db.execute(text(TIMESERIES_BY_ENTITY_SQL), entity_params).mappings().all()
        entity_action_rows = db.execute(
            text(_ACTION_BY_ENTITY_DATE_SQL), entity_params
        ).mappings().all()
        entity_action = {
            (r["entity_id"], r["period_date"]): _action_dict(r) for r in entity_action_rows
        }

        def entity_row_to_point(r):
            p = {
                "date": r["period_date"],
                "spend": _safe_float(r.get("spend")),
                "impressions": _safe_int(r.get("impressions")),
                "clicks": _safe_int(r.get("clicks")),
                "ctr": _safe_float(r.get("ctr")),
                "cpm": _safe_float(r.get("cpm")),
                "cpc": _safe_float(r.get("cpc")),
                "conversions": _safe_float(r.get("conversions")),
                "roas": _safe_float(r.get("roas")),
            }
            p.update(entity_action.get((r["entity_id"], r["period_date"]), {}))
            return _finalize_metrics(p)

        entities: dict[str, dict] = {}
        for r in entity_rows:
            eid = r["entity_id"]
            if eid not in entities:
                entities[eid] = {"entity": {"id": eid, "name": r["entity_name"] or eid}, "series": []}
            entities[eid]["series"].append(entity_row_to_point(r))

        # Per-entity previous period, aligned by date so the frontend can zip by index.
        if compare_previous:
            prior_entity_params = {**entity_params, "date_start": prior_start, "date_end": prior_end}
            prior_entity_rows = db.execute(
                text(TIMESERIES_BY_ENTITY_SQL), prior_entity_params
            ).mappings().all()
            prev_by_entity: dict[str, list] = {}
            for r in prior_entity_rows:
                prev_by_entity.setdefault(r["entity_id"], []).append(entity_row_to_point(r))
            for eid, ent in entities.items():
                ent["series"].sort(key=lambda p: p["date"])
                prev_points = sorted(prev_by_entity.get(eid, []), key=lambda p: p["date"])
                ent["previous_series"] = prev_points

        series_by_entity = list(entities.values())

    return {
        "level": level,
        "time_increment": time_increment,
        "metrics": metrics,
        "period": {"date_start": date_start, "date_stop": date_end, "preset": date_preset},
        "series": series,
        "series_by_entity": series_by_entity,
        "previous_series": previous_series,
    }


TABLE_SQL = """
WITH entity_metrics AS (
    SELECT
        md.entity_id,
        SUM(md.spend)               AS spend,
        SUM(md.impressions)         AS impressions,
        SUM(md.reach)               AS reach,
        SUM(md.clicks)              AS clicks,
        SUM(md.inline_link_clicks)  AS inline_link_clicks,
        CASE WHEN SUM(md.impressions) > 0
            THEN SUM(md.clicks)::float / SUM(md.impressions) * 100
            ELSE NULL END           AS ctr,
        CASE WHEN SUM(md.impressions) > 0
            THEN SUM(md.spend) / SUM(md.impressions) * 1000
            ELSE NULL END           AS cpm,
        CASE WHEN SUM(md.clicks) > 0
            THEN SUM(md.spend) / SUM(md.clicks)
            ELSE NULL END           AS cpc,
        CASE WHEN SUM(md.reach) > 0
            THEN SUM(md.spend) / SUM(md.reach) * 1000
            ELSE NULL END           AS cpp,
        CASE WHEN SUM(md.impressions) > 0
            THEN SUM(md.reach)::float / SUM(md.impressions)
            ELSE NULL END           AS frequency,
        SUM(conv.value)             AS conversions,
        SUM(rev.value)              AS conversion_value,
        CASE WHEN SUM(md.spend) > 0
            THEN SUM(rev.value) / SUM(md.spend)
            ELSE NULL END           AS roas,
        CASE WHEN SUM(conv.value) > 0
            THEN SUM(md.spend) / SUM(conv.value)
            ELSE NULL END           AS cpa,
        SUM(md.inline_post_engagement)  AS inline_post_engagement,
        SUM(md.estimated_ad_recallers)  AS estimated_ad_recallers
    FROM metrics_daily md
    LEFT JOIN account_configs ac ON ac.account_id = md.account_id
    LEFT JOIN metric_action_stats conv
        ON conv.entity_id = md.entity_id AND conv.entity_type = md.entity_type
        AND conv.date = md.date AND conv.field_name IN ('actions', 'conversions')
        AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
    LEFT JOIN metric_action_stats rev
        ON rev.entity_id = md.entity_id AND rev.entity_type = md.entity_type
        AND rev.date = md.date AND rev.field_name = 'action_values'
        AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
    WHERE md.account_id = :account_id
      AND md.entity_type = :entity_type
      AND md.date BETWEEN :date_start AND :date_end
    GROUP BY md.entity_id
)
SELECT
    e.*,
    c.id::text          AS entity_id_str,
    c.name              AS entity_name,
    c.status            AS entity_status,
    c.effective_status  AS entity_effective_status,
    c.objective         AS entity_objective,
    c.daily_budget      AS entity_daily_budget,
    :platform_id        AS entity_platform,
    COUNT(*) OVER()     AS total_count
FROM entity_metrics e
JOIN campaigns c ON c.id = e.entity_id
WHERE (:search IS NULL OR c.name ILIKE '%' || :search || '%')
  AND (:status IS NULL OR c.status = :status)
ORDER BY {sort_col} {sort_dir}
LIMIT :per_page OFFSET :offset
"""

# Prior-period base metrics for "compare previous". Reuses the SAME entity_metrics
# CTE body as TABLE_SQL (identical SUM/ratio definitions — ratios computed AFTER
# aggregation, never average-of-averages) but keyed by entity_id with no pagination,
# ordering, entity-table join, or search/status filter (the current-period query
# already resolved which entities are on the page; we only look up their prior
# numbers). :entity_type / :date_start / :date_end are rebound to the prior window.
_TABLE_CTE_BODY = TABLE_SQL[
    TABLE_SQL.index("WITH entity_metrics AS ("): TABLE_SQL.index("\nSELECT\n    e.*")
]
TABLE_PREV_SQL = (
    _TABLE_CTE_BODY
    + "\nSELECT e.*, e.entity_id::text AS entity_id_str FROM entity_metrics e"
)

TABLE_SQL_ADGROUP = TABLE_SQL.replace(
    "JOIN campaigns c ON c.id = e.entity_id",
    "JOIN ad_groups c ON c.id = e.entity_id\nLEFT JOIN campaigns camp ON camp.id = c.campaign_id",
).replace(
    "c.objective         AS entity_objective,\n    c.daily_budget      AS entity_daily_budget,",
    "NULL::varchar       AS entity_objective,\n    c.daily_budget      AS entity_daily_budget,",
).replace(
    ":platform_id        AS entity_platform,",
    ":platform_id        AS entity_platform,\n    camp.name           AS entity_campaign_name,\n    camp.id::text       AS entity_campaign_id,",
)

TABLE_SQL_AD = TABLE_SQL.replace(
    "JOIN campaigns c ON c.id = e.entity_id",
    "JOIN ads c ON c.id = e.entity_id\n"
    "LEFT JOIN ad_groups ag ON ag.id = c.ad_group_id\n"
    "LEFT JOIN campaigns camp ON camp.id = c.campaign_id",
).replace(
    "c.objective         AS entity_objective,\n    c.daily_budget      AS entity_daily_budget,",
    "NULL::varchar       AS entity_objective,\n    NULL::numeric       AS entity_daily_budget,",
).replace(
    ":platform_id        AS entity_platform,",
    ":platform_id        AS entity_platform,\n"
    "    ag.name             AS entity_adgroup_name,\n"
    "    ag.id::text         AS entity_adgroup_id,\n"
    "    camp.name           AS entity_campaign_name,\n"
    "    camp.id::text       AS entity_campaign_id,",
).replace(
    "LEFT JOIN campaigns camp ON camp.id = c.campaign_id",
    "LEFT JOIN campaigns camp ON camp.id = c.campaign_id\n"
    "LEFT JOIN creatives cr ON cr.id = c.creative_id",
).replace(
    "    COUNT(*) OVER()     AS total_count",
    "    cr.thumbnail_url    AS cr_thumbnail_url,\n"
    "    cr.image_url        AS cr_image_url,\n"
    "    cr.format           AS cr_format,\n"
    "    cr.title            AS cr_title,\n"
    "    cr.cta_type         AS cr_cta_type,\n"
    "    COUNT(*) OVER()     AS total_count",
)


def get_table(
    db: Session,
    account_id: str,
    org_id: str,
    date_start: date,
    date_end: date,
    level: str = "campaign",
    campaign_id: Optional[str] = None,
    adgroup_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "spend",
    sort_order: str = "desc",
    page: int = 1,
    per_page: int = 25,
    date_preset: Optional[str] = None,
    compare_previous: bool = False,
) -> tuple[list[dict], int]:
    account = assert_account_belongs_to_org(db, account_id, org_id)

    sort_col = sort_by if sort_by in VALID_SORT_COLUMNS else "spend"
    if sort_col in {"spend", "impressions", "clicks", "ctr", "cpm", "cpc", "roas", "cpa", "conversions"}:
        sort_col = f"e.{sort_col}"
    else:
        sort_col = f"c.{sort_col}"
    sort_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    entity_type = level if level in ("campaign", "adgroup", "ad") else "campaign"
    if entity_type == "campaign":
        sql_template = TABLE_SQL
    elif entity_type == "adgroup":
        sql_template = TABLE_SQL_ADGROUP
    else:
        sql_template = TABLE_SQL_AD

    sql = sql_template.format(sort_col=sort_col, sort_dir=sort_dir)

    platform_id = account.platform_id

    rows = db.execute(
        text(sql),
        {
            "account_id": uuid.UUID(account_id),
            "entity_type": entity_type,
            "date_start": date_start,
            "date_end": date_end,
            "search": search,
            "status": status,
            "per_page": per_page,
            "offset": calculate_offset(page, per_page),
            "platform_id": platform_id,
        },
    ).mappings().all()

    total = int(rows[0]["total_count"]) if rows else 0

    action_by_entity = _fetch_action_metrics(
        db,
        _ACTION_BY_ENTITY_SQL,
        {
            "account_id": uuid.UUID(account_id),
            "entity_type": entity_type,
            "date_start": date_start,
            "date_end": date_end,
        },
        key="entity_id",
    )

    def _row_metrics(base, action: dict) -> dict:
        m = {
            "spend": _safe_float(base.get("spend")),
            "impressions": _safe_int(base.get("impressions")),
            "reach": _safe_int(base.get("reach")),
            "frequency": _safe_float(base.get("frequency")),
            "clicks": _safe_int(base.get("clicks")),
            "inline_link_clicks": _safe_int(base.get("inline_link_clicks")),
            "ctr": _safe_float(base.get("ctr")),
            "cpm": _safe_float(base.get("cpm")),
            "cpc": _safe_float(base.get("cpc")),
            "cpp": _safe_float(base.get("cpp")),
            "conversions": _safe_float(base.get("conversions")),
            "conversion_value": _safe_float(base.get("conversion_value")),
            "roas": _safe_float(base.get("roas")),
            "cpa": _safe_float(base.get("cpa")),
            "inline_post_engagement": _safe_int(base.get("inline_post_engagement")),
            "estimated_ad_recallers": _safe_int(base.get("estimated_ad_recallers")),
        }
        m.update(action)
        _finalize_metrics(m)
        return m

    # Prior-period base + action metrics, keyed by entity_id, computed only when
    # comparison is requested. Same SQL/finalize path as the current period so
    # prior ratios are aggregated then divided, never averaged.
    prev_base_by_entity: dict = {}
    prev_action_by_entity: dict = {}
    if compare_previous:
        prior_start, prior_end = resolve_prior_period(date_start, date_end)
        prior_params = {
            "account_id": uuid.UUID(account_id),
            "entity_type": entity_type,
            "date_start": prior_start,
            "date_end": prior_end,
        }
        prev_rows = db.execute(text(TABLE_PREV_SQL), prior_params).mappings().all()
        prev_base_by_entity = {r["entity_id_str"]: r for r in prev_rows}
        prev_action_by_entity = _fetch_action_metrics(
            db, _ACTION_BY_ENTITY_SQL, prior_params, key="entity_id"
        )

    result = []
    for r in rows:
        eid = r["entity_id_str"]
        metrics = _row_metrics(r, action_by_entity.get(eid, {}))
        row = {
            "id": r["entity_id_str"],
            "name": r["entity_name"],
            "status": r["entity_status"],
            "effective_status": r["entity_effective_status"],
            "objective": r.get("entity_objective"),
            "daily_budget": _safe_float(r.get("entity_daily_budget")),
            "platform": r.get("entity_platform", "meta"),
            "adgroup_name": r.get("entity_adgroup_name"),
            "adgroup_id": r.get("entity_adgroup_id"),
            "campaign_name": r.get("entity_campaign_name"),
            "campaign_id": r.get("entity_campaign_id"),
            "creative_preview": {
                "thumbnail_url": r.get("cr_thumbnail_url"),
                "image_url": r.get("cr_image_url"),
                "format": r.get("cr_format"),
                "title": r.get("cr_title"),
                "cta_type": r.get("cr_cta_type"),
            } if (r.get("cr_thumbnail_url") or r.get("cr_image_url")) else None,
            "metrics": metrics,
            "period": {
                "date_start": date_start,
                "date_stop": date_end,
                "preset": date_preset,
            },
        }
        if compare_previous:
            # Same key set as `metrics`; entities absent from the prior window get
            # a dict of nulls (empty base + empty action, finalized).
            row["metrics_previous"] = _row_metrics(
                prev_base_by_entity.get(eid, {}),
                prev_action_by_entity.get(eid, {}),
            )
            # If one window had action rows and the other didn't, their raw
            # action-count keys diverge; union them so both dicts match.
            _align_keys(metrics, row["metrics_previous"])
        result.append(row)

    return result, total


def get_breakdown(
    db: Session,
    account_id: str,
    org_id: str,
    date_start: date,
    date_end: date,
    breakdown_type: str,
    level: str = "account",
    campaign_id: Optional[str] = None,
    adgroup_id: Optional[str] = None,
    date_preset: Optional[str] = None,
) -> dict:
    assert_account_belongs_to_org(db, account_id, org_id)

    entity_filter = ""
    params: dict = {
        "account_id": uuid.UUID(account_id),
        "date_start": date_start,
        "date_end": date_end,
        "breakdown_type": breakdown_type,
    }

    if campaign_id:
        entity_filter = "AND mb.entity_id = :entity_id"
        params["entity_id"] = uuid.UUID(campaign_id)

    sql = f"""
    SELECT
        mb.breakdown_value,
        mb.breakdown_type,
        SUM(mb.impressions)     AS impressions,
        SUM(mb.reach)           AS reach,
        SUM(mb.clicks)          AS clicks,
        SUM(mb.spend)           AS spend,
        SUM(mb.conversions)     AS conversions,
        CASE WHEN SUM(mb.impressions) > 0
            THEN SUM(mb.clicks)::float / SUM(mb.impressions) * 100
            ELSE NULL END       AS ctr,
        CASE WHEN SUM(mb.impressions) > 0
            THEN SUM(mb.spend) / SUM(mb.impressions) * 1000
            ELSE NULL END       AS cpm,
        CASE WHEN SUM(mb.clicks) > 0
            THEN SUM(mb.spend) / SUM(mb.clicks)
            ELSE NULL END       AS cpc
    FROM metric_breakdowns mb
    WHERE mb.account_id = :account_id
      AND mb.breakdown_type = :breakdown_type
      AND mb.date BETWEEN :date_start AND :date_end
      {entity_filter}
    GROUP BY mb.breakdown_value, mb.breakdown_type
    ORDER BY SUM(mb.spend) DESC NULLS LAST
    """

    rows = db.execute(text(sql), params).mappings().all()

    def parse_dimensions(bv: str, bt: str) -> dict[str, str]:
        if bt == "age_gender" and "__" in bv:
            parts = bv.split("__", 1)
            return {"age": parts[0], "gender": parts[1]}
        if bt == "platform_position" and "__" in bv:
            parts = bv.split("__", 1)
            return {"publisher_platform": parts[0], "platform_position": parts[1]}
        return {bt: bv}

    breakdown_rows = [
        {
            "breakdown_value": r["breakdown_value"],
            "dimensions": parse_dimensions(r["breakdown_value"], breakdown_type),
            "metrics": {
                "impressions": _safe_int(r.get("impressions")),
                "reach": _safe_int(r.get("reach")),
                "clicks": _safe_int(r.get("clicks")),
                "spend": _safe_float(r.get("spend")),
                "conversions": _safe_float(r.get("conversions")),
                "ctr": _safe_float(r.get("ctr")),
                "cpm": _safe_float(r.get("cpm")),
                "cpc": _safe_float(r.get("cpc")),
            },
        }
        for r in rows
    ]

    return {
        "breakdown": breakdown_type,
        "level": level,
        "period": {"date_start": date_start, "date_stop": date_end, "preset": date_preset},
        "rows": breakdown_rows,
    }


# ─── Combined (cross-platform) insights ─────────────────────────────────────────
#
# Aggregates the platform-agnostic ("combinable") metric set across a user-selected
# set of accounts. Monetary metrics may only be summed when every selected account
# shares one currency — otherwise the caller degrades to a per-account view. The
# conv/rev joins resolve each account's own conversion action via the per-row
# account_configs join, so combining accounts stays correct. Meta-only fields
# (e.g. outbound_clicks) are intentionally omitted.

_COMBINED_METRIC_SELECT = """
    SUM(md.impressions)         AS impressions,
    SUM(md.reach)               AS reach,
    SUM(md.clicks)              AS clicks,
    SUM(md.spend)               AS spend,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.clicks)::float / SUM(md.impressions) * 100
        ELSE NULL END           AS ctr,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.spend) / SUM(md.impressions) * 1000
        ELSE NULL END           AS cpm,
    CASE WHEN SUM(md.clicks) > 0
        THEN SUM(md.spend) / SUM(md.clicks)
        ELSE NULL END           AS cpc,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.reach)::float / SUM(md.impressions)
        ELSE NULL END           AS frequency,
    SUM(conv.value)             AS conversions,
    SUM(rev.value)              AS conversion_value,
    CASE WHEN SUM(md.spend) > 0
        THEN SUM(rev.value) / SUM(md.spend)
        ELSE NULL END           AS roas,
    CASE WHEN SUM(conv.value) > 0
        THEN SUM(md.spend) / SUM(conv.value)
        ELSE NULL END           AS cpa,
    MAX(md.fetched_at)          AS cached_at
"""

_COMBINED_JOINS = """
FROM metrics_daily md
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id AND conv.entity_type = md.entity_type
    AND conv.date = md.date AND conv.field_name IN ('actions', 'conversions')
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id AND rev.entity_type = md.entity_type
    AND rev.date = md.date AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
WHERE md.account_id IN :account_ids
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
"""

COMBINED_OVERVIEW_SQL = f"SELECT{_COMBINED_METRIC_SELECT}{_COMBINED_JOINS}"

COMBINED_PER_ACCOUNT_SQL = (
    f"SELECT\n    md.account_id::text AS account_id,{_COMBINED_METRIC_SELECT}"
    f"{_COMBINED_JOINS}\nGROUP BY md.account_id"
)

COMBINED_TIMESERIES_SQL = f"""
SELECT
    date_trunc(:increment, md.date)::date   AS period_date,
    SUM(md.impressions)                     AS impressions,
    SUM(md.reach)                           AS reach,
    SUM(md.clicks)                          AS clicks,
    SUM(md.spend)                           AS spend,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.clicks)::float / SUM(md.impressions) * 100
        ELSE NULL END                       AS ctr,
    CASE WHEN SUM(md.impressions) > 0
        THEN SUM(md.spend) / SUM(md.impressions) * 1000
        ELSE NULL END                       AS cpm,
    CASE WHEN SUM(md.clicks) > 0
        THEN SUM(md.spend) / SUM(md.clicks)
        ELSE NULL END                       AS cpc,
    SUM(conv.value)                         AS conversions,
    CASE WHEN SUM(md.spend) > 0
        THEN SUM(rev.value) / SUM(md.spend)
        ELSE NULL END                       AS roas
FROM metrics_daily md
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id AND conv.entity_type = md.entity_type
    AND conv.date = md.date AND conv.field_name IN ('actions', 'conversions')
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id AND rev.entity_type = md.entity_type
    AND rev.date = md.date AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
WHERE md.account_id IN :account_ids
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
GROUP BY period_date
ORDER BY period_date
"""


def _combined_summary(r) -> dict:
    return {
        "spend": _safe_float(r.get("spend")),
        "impressions": _safe_int(r.get("impressions")),
        "reach": _safe_int(r.get("reach")),
        "frequency": _safe_float(r.get("frequency")),
        "clicks": _safe_int(r.get("clicks")),
        "ctr": _safe_float(r.get("ctr")),
        "cpm": _safe_float(r.get("cpm")),
        "cpc": _safe_float(r.get("cpc")),
        "conversions": _safe_float(r.get("conversions")),
        "conversion_value": _safe_float(r.get("conversion_value")),
        "roas": _safe_float(r.get("roas")),
        "cpa": _safe_float(r.get("cpa")),
    }


def _resolve_org_accounts(db: Session, account_ids: list[str], org_id: str) -> list[Account]:
    """Validate every account belongs to the org; returns the Account rows."""
    return [assert_account_belongs_to_org(db, a, org_id) for a in account_ids]


def get_combined_overview(
    db: Session,
    account_ids: list[str],
    org_id: str,
    date_start: date,
    date_end: date,
    date_preset: Optional[str] = None,
) -> dict:
    accounts = _resolve_org_accounts(db, account_ids, org_id)
    period = {"date_start": date_start, "date_stop": date_end, "preset": date_preset}

    if not accounts:
        return {
            "combined": False,
            "currency_mismatch": False,
            "currency": None,
            "currencies": [],
            "period": period,
            "summary": _combined_summary({}),
            "vs_previous": {},
            "per_account": [],
            "account_count": 0,
            "cached_at": None,
        }

    acc_by_id = {str(a.id): a for a in accounts}
    uuids = [a.id for a in accounts]
    base_params = {
        "account_ids": uuids,
        "date_start": date_start,
        "date_end": date_end,
    }

    per_stmt = text(COMBINED_PER_ACCOUNT_SQL).bindparams(
        bindparam("account_ids", expanding=True)
    )
    per_rows = db.execute(per_stmt, base_params).mappings().all()

    per_account = []
    cached_candidates = []
    for r in per_rows:
        a = acc_by_id.get(r["account_id"])
        if r.get("cached_at"):
            cached_candidates.append(r["cached_at"])
        per_account.append({
            "account_id": r["account_id"],
            "name": a.name if a else r["account_id"],
            "platform": a.platform_id if a else None,
            "currency": a.currency if a else None,
            "summary": _combined_summary(r),
        })
    cached_at = max(cached_candidates) if cached_candidates else None

    currencies = sorted({a.currency for a in accounts})
    combined = len(currencies) == 1

    if not combined:
        return {
            "combined": False,
            "currency_mismatch": True,
            "currency": None,
            "currencies": currencies,
            "period": period,
            "summary": _combined_summary({}),
            "vs_previous": {},
            "per_account": per_account,
            "account_count": len(accounts),
            "cached_at": cached_at,
        }

    agg_stmt = text(COMBINED_OVERVIEW_SQL).bindparams(
        bindparam("account_ids", expanding=True)
    )
    row = db.execute(agg_stmt, base_params).mappings().first()
    prior_start, prior_end = resolve_prior_period(date_start, date_end)
    prior_row = db.execute(
        agg_stmt, {**base_params, "date_start": prior_start, "date_end": prior_end}
    ).mappings().first()

    summary = _combined_summary(row) if row else _combined_summary({})
    prev = _combined_summary(prior_row) if prior_row else {}

    return {
        "combined": True,
        "currency_mismatch": False,
        "currency": currencies[0],
        "currencies": currencies,
        "period": period,
        "summary": summary,
        "vs_previous": {
            "spend": _pct_change(summary.get("spend"), prev.get("spend")),
            "impressions": _pct_change(summary.get("impressions"), prev.get("impressions")),
            "clicks": _pct_change(summary.get("clicks"), prev.get("clicks")),
            "ctr": _pct_change(summary.get("ctr"), prev.get("ctr")),
            "conversions": _pct_change(summary.get("conversions"), prev.get("conversions")),
            "roas": _pct_change(summary.get("roas"), prev.get("roas")),
        },
        "per_account": per_account,
        "account_count": len(accounts),
        "cached_at": cached_at,
    }


def get_combined_timeseries(
    db: Session,
    account_ids: list[str],
    org_id: str,
    date_start: date,
    date_end: date,
    time_increment: str = "day",
    date_preset: Optional[str] = None,
) -> dict:
    accounts = _resolve_org_accounts(db, account_ids, org_id)
    currencies = sorted({a.currency for a in accounts}) if accounts else []
    combined = len(currencies) == 1
    period = {"date_start": date_start, "date_stop": date_end, "preset": date_preset}

    if not accounts:
        return {
            "combined": False,
            "currency_mismatch": False,
            "currency": None,
            "currencies": [],
            "period": period,
            "series": [],
        }

    pg_increment = {"day": "day", "week": "week", "month": "month"}.get(time_increment, "day")
    stmt = text(COMBINED_TIMESERIES_SQL).bindparams(
        bindparam("account_ids", expanding=True)
    )
    rows = db.execute(
        stmt,
        {
            "account_ids": [a.id for a in accounts],
            "date_start": date_start,
            "date_end": date_end,
            "increment": pg_increment,
        },
    ).mappings().all()

    # Never sum monetary metrics across mixed currencies — null them out.
    money_null = not combined

    def point(r):
        return {
            "date": r["period_date"],
            "spend": None if money_null else _safe_float(r.get("spend")),
            "impressions": _safe_int(r.get("impressions")),
            "clicks": _safe_int(r.get("clicks")),
            "ctr": _safe_float(r.get("ctr")),
            "cpm": None if money_null else _safe_float(r.get("cpm")),
            "cpc": None if money_null else _safe_float(r.get("cpc")),
            "reach": _safe_int(r.get("reach")),
            "conversions": _safe_float(r.get("conversions")),
            "roas": None if money_null else _safe_float(r.get("roas")),
        }

    return {
        "combined": combined,
        "currency_mismatch": not combined,
        "currency": currencies[0] if combined else None,
        "currencies": currencies,
        "period": period,
        "series": [point(r) for r in rows],
    }


# ─── Engagement (TikTok-only curated view) ──────────────────────────────────────
#
# TikTok stores social engagement as metric_action_stats rows with
# field_name='actions' and action_type in (like, comment, share) — see
# TIKTOK_ACTION_MAP in workers/tasks/tiktok_insights.py.

ENGAGEMENT_TOTALS_SQL = """
SELECT mas.action_type AS action_type, SUM(mas.value) AS value
FROM metric_action_stats mas
WHERE mas.account_id = :account_id
  AND mas.field_name = 'actions'
  AND mas.action_type IN ('like', 'comment', 'share', 'follow', 'profile_visit')
  AND mas.date BETWEEN :date_start AND :date_end
GROUP BY mas.action_type
"""

ENGAGEMENT_IMPRESSIONS_SQL = """
SELECT SUM(md.impressions) AS impressions, MAX(md.fetched_at) AS cached_at
FROM metrics_daily md
WHERE md.account_id = :account_id
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
"""

ENGAGEMENT_SERIES_SQL = """
SELECT mas.date AS date, SUM(mas.value) AS engagements
FROM metric_action_stats mas
WHERE mas.account_id = :account_id
  AND mas.field_name = 'actions'
  AND mas.action_type IN ('like', 'comment', 'share')
  AND mas.date BETWEEN :date_start AND :date_end
GROUP BY mas.date
ORDER BY mas.date
"""


def get_engagement(
    db: Session,
    account_id: str,
    org_id: str,
    date_start: date,
    date_end: date,
    date_preset: Optional[str] = None,
) -> dict:
    assert_account_belongs_to_org(db, account_id, org_id)
    params = {
        "account_id": uuid.UUID(account_id),
        "date_start": date_start,
        "date_end": date_end,
    }

    totals_rows = db.execute(text(ENGAGEMENT_TOTALS_SQL), params).mappings().all()
    totals = {r["action_type"]: _safe_float(r["value"]) for r in totals_rows}
    likes = totals.get("like")
    comments = totals.get("comment")
    shares = totals.get("share")
    follows = totals.get("follow")
    profile_visits = totals.get("profile_visit")
    total_engagements = sum(v for v in (likes, comments, shares) if v is not None) or None

    imp_row = db.execute(text(ENGAGEMENT_IMPRESSIONS_SQL), params).mappings().first()
    impressions = _safe_int(imp_row.get("impressions")) if imp_row else None
    cached_at = imp_row.get("cached_at") if imp_row else None

    engagement_rate = None
    if total_engagements and impressions:
        engagement_rate = round(total_engagements / impressions * 100, 4)

    series_rows = db.execute(text(ENGAGEMENT_SERIES_SQL), params).mappings().all()
    series = [
        {"date": r["date"], "engagements": _safe_float(r.get("engagements"))}
        for r in series_rows
    ]

    return {
        "period": {"date_start": date_start, "date_stop": date_end, "preset": date_preset},
        "summary": {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "follows": follows,
            "profile_visits": profile_visits,
            "total_engagements": total_engagements,
            "impressions": impressions,
            "engagement_rate": engagement_rate,
        },
        "series": series,
        "cached_at": cached_at,
    }
