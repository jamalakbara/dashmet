from datetime import date
from typing import Any, Optional
from pydantic import BaseModel


class MetricsSummary(BaseModel):
    spend: Optional[float] = None
    impressions: Optional[int] = None
    reach: Optional[int] = None
    frequency: Optional[float] = None
    clicks: Optional[int] = None
    inline_link_clicks: Optional[int] = None
    ctr: Optional[float] = None
    cpm: Optional[float] = None
    cpc: Optional[float] = None
    cpp: Optional[float] = None
    conversions: Optional[float] = None
    conversion_value: Optional[float] = None
    roas: Optional[float] = None
    cpa: Optional[float] = None


class VsPrevious(BaseModel):
    spend: Optional[float] = None
    impressions: Optional[float] = None
    clicks: Optional[float] = None
    ctr: Optional[float] = None
    conversions: Optional[float] = None
    roas: Optional[float] = None


class TopCampaignRow(BaseModel):
    id: str
    name: str
    spend: Optional[float] = None
    conversions: Optional[float] = None
    roas: Optional[float] = None


class PeriodInfo(BaseModel):
    date_start: date
    date_stop: date
    preset: Optional[str] = None


class OverviewResponse(BaseModel):
    period: PeriodInfo
    summary: MetricsSummary
    vs_previous: VsPrevious
    top_campaigns: list[TopCampaignRow]


class TimeSeriesPoint(BaseModel):
    date: date
    spend: Optional[float] = None
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    ctr: Optional[float] = None
    cpm: Optional[float] = None
    cpc: Optional[float] = None
    reach: Optional[int] = None
    conversions: Optional[float] = None
    roas: Optional[float] = None


class TimeSeriesEntity(BaseModel):
    entity: dict[str, str]
    series: list[TimeSeriesPoint]


class TimeSeriesResponse(BaseModel):
    level: str
    time_increment: str
    metrics: list[str]
    period: PeriodInfo
    series: Optional[list[TimeSeriesPoint]] = None
    series_by_entity: Optional[list[TimeSeriesEntity]] = None
    previous_series: Optional[list[TimeSeriesPoint]] = None


class TableMetrics(BaseModel):
    spend: Optional[float] = None
    impressions: Optional[int] = None
    reach: Optional[int] = None
    frequency: Optional[float] = None
    clicks: Optional[int] = None
    inline_link_clicks: Optional[int] = None
    ctr: Optional[float] = None
    cpm: Optional[float] = None
    cpc: Optional[float] = None
    cpp: Optional[float] = None
    conversions: Optional[float] = None
    conversion_value: Optional[float] = None
    roas: Optional[float] = None
    cpa: Optional[float] = None


class TableRow(BaseModel):
    id: str
    name: str
    status: str
    effective_status: str
    platform: str
    metrics: TableMetrics
    period: PeriodInfo
    # Campaign-specific
    objective: Optional[str] = None
    daily_budget: Optional[float] = None
    # Ad-specific
    creative_preview: Optional[Any] = None


class BreakdownDimensions(BaseModel):
    age: Optional[str] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    publisher_platform: Optional[str] = None
    platform_position: Optional[str] = None
    device_platform: Optional[str] = None


class BreakdownMetrics(BaseModel):
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    spend: Optional[float] = None
    ctr: Optional[float] = None
    cpm: Optional[float] = None
    cpc: Optional[float] = None


class BreakdownRow(BaseModel):
    breakdown_value: str
    dimensions: dict[str, str]
    metrics: BreakdownMetrics


class BreakdownResponse(BaseModel):
    breakdown: str
    level: str
    period: PeriodInfo
    rows: list[BreakdownRow]
