"""Unit tests for the Google Ads sync mapping logic (no network / SDK needed)."""
import uuid
from datetime import date
from decimal import Decimal

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
