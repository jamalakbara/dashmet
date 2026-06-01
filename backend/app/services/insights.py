import uuid
from datetime import date, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.exceptions import ForbiddenError, NotFoundError
from app.models.platform import Account
from app.schemas.common import calculate_offset
from app.services.accounts import assert_account_belongs_to_org

VALID_SORT_COLUMNS = {
    "spend", "impressions", "clicks", "ctr", "cpm", "cpc", "cpp",
    "reach", "roas", "cpa", "conversions", "name", "status",
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
        "last_7d": (today - timedelta(days=6), today),
        "last_14d": (today - timedelta(days=13), today),
        "last_28d": (today - timedelta(days=27), today),
        "last_30d": (today - timedelta(days=29), today),
        "last_90d": (today - timedelta(days=89), today),
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


def resolve_prior_period(start: date, end: date) -> tuple[date, date]:
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
        ELSE NULL END           AS cpa
FROM metrics_daily md
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id
    AND conv.entity_type = md.entity_type
    AND conv.date = md.date
    AND conv.field_name = 'actions'
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id
    AND rev.entity_type = md.entity_type
    AND rev.date = md.date
    AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
WHERE md.account_id = :account_id
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
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
        ELSE NULL END   AS roas
FROM metrics_daily md
JOIN campaigns c ON c.id = md.entity_id
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id
    AND conv.entity_type = 'campaign'
    AND conv.date = md.date
    AND conv.field_name = 'actions'
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id
    AND rev.entity_type = 'campaign'
    AND rev.date = md.date
    AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
WHERE md.account_id = :account_id
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
GROUP BY c.id, c.name
ORDER BY SUM(md.spend) DESC NULLS LAST
LIMIT 5
"""


def get_overview(
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

    row = db.execute(text(OVERVIEW_SQL), params).mappings().first()
    prior_start, prior_end = resolve_prior_period(date_start, date_end)
    prior_params = {**params, "date_start": prior_start, "date_end": prior_end}
    prior_row = db.execute(text(OVERVIEW_SQL), prior_params).mappings().first()

    top = db.execute(text(TOP_CAMPAIGNS_SQL), params).mappings().all()

    def row_to_dict(r):
        if not r:
            return {}
        return {k: _safe_float(v) for k, v in r.items()}

    curr = row_to_dict(row)
    prev = row_to_dict(prior_row)

    return {
        "period": {
            "date_start": date_start,
            "date_stop": date_end,
            "preset": date_preset,
        },
        "summary": {
            "spend": curr.get("spend"),
            "impressions": _safe_int(curr.get("impressions")),
            "reach": _safe_int(curr.get("reach")),
            "frequency": curr.get("frequency"),
            "clicks": _safe_int(curr.get("clicks")),
            "inline_link_clicks": _safe_int(curr.get("inline_link_clicks")),
            "ctr": curr.get("ctr"),
            "cpm": curr.get("cpm"),
            "cpc": curr.get("cpc"),
            "cpp": curr.get("cpp"),
            "conversions": curr.get("conversions"),
            "conversion_value": curr.get("conversion_value"),
            "roas": curr.get("roas"),
            "cpa": curr.get("cpa"),
        },
        "vs_previous": {
            "spend": _pct_change(curr.get("spend"), prev.get("spend")),
            "impressions": _pct_change(curr.get("impressions"), prev.get("impressions")),
            "clicks": _pct_change(curr.get("clicks"), prev.get("clicks")),
            "ctr": _pct_change(curr.get("ctr"), prev.get("ctr")),
            "conversions": _pct_change(curr.get("conversions"), prev.get("conversions")),
            "roas": _pct_change(curr.get("roas"), prev.get("roas")),
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
        ELSE NULL END                       AS roas
FROM metrics_daily md
LEFT JOIN account_configs ac ON ac.account_id = md.account_id
LEFT JOIN metric_action_stats conv
    ON conv.entity_id = md.entity_id AND conv.entity_type = md.entity_type
    AND conv.date = md.date AND conv.field_name = 'actions'
    AND conv.action_type = COALESCE(ac.primary_conversion_action, 'purchase')
LEFT JOIN metric_action_stats rev
    ON rev.entity_id = md.entity_id AND rev.entity_type = md.entity_type
    AND rev.date = md.date AND rev.field_name = 'action_values'
    AND rev.action_type = COALESCE(ac.roas_action_type, 'purchase')
WHERE md.account_id = :account_id
  AND md.entity_type = 'campaign'
  AND md.date BETWEEN :date_start AND :date_end
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
    AND conv.date = md.date AND conv.field_name = 'actions'
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
) -> dict:
    assert_account_belongs_to_org(db, account_id, org_id)
    increment_map = {"day": "day", "week": "week", "month": "month"}
    pg_increment = increment_map.get(time_increment, "day")

    params = {
        "account_id": uuid.UUID(account_id),
        "date_start": date_start,
        "date_end": date_end,
        "increment": pg_increment,
    }
    rows = db.execute(text(TIMESERIES_SQL), params).mappings().all()

    def row_to_point(r):
        return {
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
        }

    series = [row_to_point(r) for r in rows]
    previous_series = None
    series_by_entity = None

    if compare_previous:
        prior_start, prior_end = resolve_prior_period(date_start, date_end)
        prior_params = {**params, "date_start": prior_start, "date_end": prior_end}
        prior_rows = db.execute(text(TIMESERIES_SQL), prior_params).mappings().all()
        previous_series = [row_to_point(r) for r in prior_rows]

    if level != "account":
        entity_type_map = {"campaign": "campaign", "adgroup": "adgroup", "ad": "ad"}
        entity_type = entity_type_map.get(level, "campaign")
        entity_params = {**params, "entity_type": entity_type}
        entity_rows = db.execute(text(TIMESERIES_BY_ENTITY_SQL), entity_params).mappings().all()

        entities: dict[str, dict] = {}
        for r in entity_rows:
            eid = r["entity_id"]
            if eid not in entities:
                entities[eid] = {"entity": {"id": eid, "name": r["entity_name"] or eid}, "series": []}
            entities[eid]["series"].append({
                "date": r["period_date"],
                "spend": _safe_float(r.get("spend")),
                "impressions": _safe_int(r.get("impressions")),
                "clicks": _safe_int(r.get("clicks")),
                "ctr": _safe_float(r.get("ctr")),
                "cpm": _safe_float(r.get("cpm")),
                "cpc": _safe_float(r.get("cpc")),
                "conversions": _safe_float(r.get("conversions")),
                "roas": _safe_float(r.get("roas")),
            })
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
            ELSE NULL END           AS cpa
    FROM metrics_daily md
    LEFT JOIN account_configs ac ON ac.account_id = md.account_id
    LEFT JOIN metric_action_stats conv
        ON conv.entity_id = md.entity_id AND conv.entity_type = md.entity_type
        AND conv.date = md.date AND conv.field_name = 'actions'
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
) -> tuple[list[dict], int]:
    assert_account_belongs_to_org(db, account_id, org_id)

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

    platform_id = "meta"

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

    result = []
    for r in rows:
        result.append({
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
            "metrics": {
                "spend": _safe_float(r.get("spend")),
                "impressions": _safe_int(r.get("impressions")),
                "reach": _safe_int(r.get("reach")),
                "frequency": _safe_float(r.get("frequency")),
                "clicks": _safe_int(r.get("clicks")),
                "inline_link_clicks": _safe_int(r.get("inline_link_clicks")),
                "ctr": _safe_float(r.get("ctr")),
                "cpm": _safe_float(r.get("cpm")),
                "cpc": _safe_float(r.get("cpc")),
                "cpp": _safe_float(r.get("cpp")),
                "conversions": _safe_float(r.get("conversions")),
                "conversion_value": _safe_float(r.get("conversion_value")),
                "roas": _safe_float(r.get("roas")),
                "cpa": _safe_float(r.get("cpa")),
            },
            "period": {
                "date_start": date_start,
                "date_stop": date_end,
                "preset": date_preset,
            },
        })

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
        SUM(mb.clicks)          AS clicks,
        SUM(mb.spend)           AS spend,
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
                "clicks": _safe_int(r.get("clicks")),
                "spend": _safe_float(r.get("spend")),
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
