from datetime import date, datetime
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
    outbound_clicks: Optional[float] = None
    outbound_clicks_ctr: Optional[float] = None
    # ── Extended action-based + computed metrics (Meta + TikTok) ──
    add_to_cart: Optional[int] = None
    initiate_checkout: Optional[int] = None
    landing_page_views: Optional[int] = None
    leads: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    follows: Optional[int] = None
    profile_visits: Optional[int] = None
    result: Optional[int] = None
    web_purchases: Optional[int] = None
    web_add_to_cart: Optional[int] = None
    app_installs: Optional[int] = None
    web_purchase_value: Optional[float] = None
    video_views: Optional[int] = None
    video_p25: Optional[int] = None
    video_p50: Optional[int] = None
    video_p75: Optional[int] = None
    video_p100: Optional[int] = None
    video_thruplays: Optional[int] = None
    video_2s: Optional[int] = None
    video_2s_views: Optional[int] = None
    video_6s_views: Optional[int] = None
    video_avg_time: Optional[float] = None
    avg_watch_time: Optional[float] = None
    post_reactions: Optional[int] = None
    post_saves: Optional[int] = None
    add_to_cart_value: Optional[float] = None
    avg_basket_price: Optional[float] = None
    conversion_rate: Optional[float] = None
    engagement_rate: Optional[float] = None
    cost_per_result: Optional[float] = None
    install_cost: Optional[float] = None
    inline_post_engagement: Optional[int] = None
    cost_per_inline_post_engagement: Optional[float] = None
    estimated_ad_recallers: Optional[int] = None
    estimated_ad_recall_rate: Optional[float] = None
    # ── Funnel events + cost-per-step ──
    view_content: Optional[int] = None
    purchase: Optional[int] = None
    search: Optional[int] = None
    complete_registration: Optional[int] = None
    web_checkout: Optional[int] = None
    cost_per_view_content: Optional[float] = None
    cost_per_add_to_cart: Optional[float] = None
    cost_per_initiate_checkout: Optional[float] = None
    cost_per_purchase: Optional[float] = None
    cost_per_landing_page_view: Optional[float] = None
    cost_per_lead: Optional[float] = None
    cost_per_web_purchase: Optional[float] = None
    cost_per_web_add_to_cart: Optional[float] = None
    # ── TikTok onsite/shop events + values + computed ratios ──
    page_view_onsite: Optional[int] = None
    web_add_to_cart_value: Optional[float] = None
    web_checkout_value: Optional[float] = None
    avg_watch_time_per_user: Optional[float] = None
    roas_shop: Optional[float] = None
    cost_per_web_checkout: Optional[float] = None
    # ── CPAS "Shared Item" (catalog-segment) events + cost-per-step + ROAS ──
    purchase_shared: Optional[int] = None
    add_to_cart_shared: Optional[int] = None
    content_view_shared: Optional[int] = None
    purchase_value_shared: Optional[float] = None
    add_to_cart_value_shared: Optional[float] = None
    cost_per_purchase_shared: Optional[float] = None
    cost_per_add_to_cart_shared: Optional[float] = None
    cost_per_content_view_shared: Optional[float] = None
    roas_shared: Optional[float] = None
    # ── TikTok engagement / interactive / LIVE counts ──
    total_engagement: Optional[int] = None
    product_clicks_ix: Optional[int] = None
    live_views_10s: Optional[int] = None
    live_product_clicks: Optional[int] = None


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
    status: Optional[str] = None
    spend: Optional[float] = None
    impressions: Optional[int] = None
    ctr: Optional[float] = None
    conversions: Optional[float] = None
    roas: Optional[float] = None


class PeriodInfo(BaseModel):
    date_start: date
    date_stop: date
    preset: Optional[str] = None


class OverviewResponse(BaseModel):
    period: PeriodInfo
    summary: MetricsSummary
    previous: MetricsSummary
    vs_previous: VsPrevious
    top_campaigns: list[TopCampaignRow]


class OverviewSummaryResponse(BaseModel):
    """On-demand AI diagnosis over the overview numbers (P-1 envelope: carries
    the same period as the numbers it narrates, plus model/generation stamp so
    the client can show provenance).

    Structured into four diagnostic fields rather than one prose blob so the card
    can present a headline finding, its likely driver, a secondary watch signal,
    and a recommended next step distinctly.

    `data_as_of` is the freshness token the diagnosis was generated against
    (MAX fetched_at over the period, from get_overview) — a re-sync moves it, so
    a stale narrative is never served (P-1). `cached` tells the client whether
    this response was replayed from the Redis cache vs freshly generated."""
    headline: str
    driver: str
    watch: str
    next_step: str
    period: PeriodInfo
    model: str
    generated_at: datetime
    data_as_of: Optional[datetime] = None
    cached: bool = False


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
    outbound_clicks: Optional[float] = None
    outbound_clicks_ctr: Optional[float] = None
    # ── Extended action-based + computed metrics (Meta + TikTok) ──
    add_to_cart: Optional[int] = None
    initiate_checkout: Optional[int] = None
    landing_page_views: Optional[int] = None
    leads: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    follows: Optional[int] = None
    profile_visits: Optional[int] = None
    result: Optional[int] = None
    web_purchases: Optional[int] = None
    web_add_to_cart: Optional[int] = None
    app_installs: Optional[int] = None
    web_purchase_value: Optional[float] = None
    video_views: Optional[int] = None
    video_p25: Optional[int] = None
    video_p50: Optional[int] = None
    video_p75: Optional[int] = None
    video_p100: Optional[int] = None
    video_thruplays: Optional[int] = None
    video_2s: Optional[int] = None
    video_2s_views: Optional[int] = None
    video_6s_views: Optional[int] = None
    video_avg_time: Optional[float] = None
    avg_watch_time: Optional[float] = None
    post_reactions: Optional[int] = None
    post_saves: Optional[int] = None
    add_to_cart_value: Optional[float] = None
    avg_basket_price: Optional[float] = None
    conversion_rate: Optional[float] = None
    engagement_rate: Optional[float] = None
    cost_per_result: Optional[float] = None
    install_cost: Optional[float] = None
    inline_post_engagement: Optional[int] = None
    cost_per_inline_post_engagement: Optional[float] = None
    estimated_ad_recallers: Optional[int] = None
    estimated_ad_recall_rate: Optional[float] = None
    # ── Funnel events + cost-per-step ──
    view_content: Optional[int] = None
    purchase: Optional[int] = None
    search: Optional[int] = None
    complete_registration: Optional[int] = None
    web_checkout: Optional[int] = None
    cost_per_view_content: Optional[float] = None
    cost_per_add_to_cart: Optional[float] = None
    cost_per_initiate_checkout: Optional[float] = None
    cost_per_purchase: Optional[float] = None
    cost_per_landing_page_view: Optional[float] = None
    cost_per_lead: Optional[float] = None
    cost_per_web_purchase: Optional[float] = None
    cost_per_web_add_to_cart: Optional[float] = None
    # ── TikTok onsite/shop events + values + computed ratios ──
    page_view_onsite: Optional[int] = None
    web_add_to_cart_value: Optional[float] = None
    web_checkout_value: Optional[float] = None
    avg_watch_time_per_user: Optional[float] = None
    roas_shop: Optional[float] = None
    cost_per_web_checkout: Optional[float] = None
    # ── CPAS "Shared Item" (catalog-segment) events + cost-per-step + ROAS ──
    purchase_shared: Optional[int] = None
    add_to_cart_shared: Optional[int] = None
    content_view_shared: Optional[int] = None
    purchase_value_shared: Optional[float] = None
    add_to_cart_value_shared: Optional[float] = None
    cost_per_purchase_shared: Optional[float] = None
    cost_per_add_to_cart_shared: Optional[float] = None
    cost_per_content_view_shared: Optional[float] = None
    roas_shared: Optional[float] = None
    # ── TikTok engagement / interactive / LIVE counts ──
    total_engagement: Optional[int] = None
    product_clicks_ix: Optional[int] = None
    live_views_10s: Optional[int] = None
    live_product_clicks: Optional[int] = None


class TimeSeriesEntity(BaseModel):
    entity: dict[str, str]
    series: list[TimeSeriesPoint]
    previous_series: Optional[list[TimeSeriesPoint]] = None


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
    # ── Extended action-based + computed metrics (Meta + TikTok) ──
    add_to_cart: Optional[int] = None
    initiate_checkout: Optional[int] = None
    landing_page_views: Optional[int] = None
    leads: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    follows: Optional[int] = None
    profile_visits: Optional[int] = None
    result: Optional[int] = None
    web_purchases: Optional[int] = None
    web_add_to_cart: Optional[int] = None
    app_installs: Optional[int] = None
    web_purchase_value: Optional[float] = None
    video_views: Optional[int] = None
    video_p25: Optional[int] = None
    video_p50: Optional[int] = None
    video_p75: Optional[int] = None
    video_p100: Optional[int] = None
    video_thruplays: Optional[int] = None
    video_2s: Optional[int] = None
    video_2s_views: Optional[int] = None
    video_6s_views: Optional[int] = None
    video_avg_time: Optional[float] = None
    avg_watch_time: Optional[float] = None
    post_reactions: Optional[int] = None
    post_saves: Optional[int] = None
    add_to_cart_value: Optional[float] = None
    avg_basket_price: Optional[float] = None
    conversion_rate: Optional[float] = None
    engagement_rate: Optional[float] = None
    cost_per_result: Optional[float] = None
    install_cost: Optional[float] = None
    inline_post_engagement: Optional[int] = None
    cost_per_inline_post_engagement: Optional[float] = None
    estimated_ad_recallers: Optional[int] = None
    estimated_ad_recall_rate: Optional[float] = None
    # ── Funnel events + cost-per-step ──
    view_content: Optional[int] = None
    purchase: Optional[int] = None
    search: Optional[int] = None
    complete_registration: Optional[int] = None
    web_checkout: Optional[int] = None
    cost_per_view_content: Optional[float] = None
    cost_per_add_to_cart: Optional[float] = None
    cost_per_initiate_checkout: Optional[float] = None
    cost_per_purchase: Optional[float] = None
    cost_per_landing_page_view: Optional[float] = None
    cost_per_lead: Optional[float] = None
    cost_per_web_purchase: Optional[float] = None
    cost_per_web_add_to_cart: Optional[float] = None
    # ── TikTok onsite/shop events + values + computed ratios ──
    page_view_onsite: Optional[int] = None
    web_add_to_cart_value: Optional[float] = None
    web_checkout_value: Optional[float] = None
    avg_watch_time_per_user: Optional[float] = None
    roas_shop: Optional[float] = None
    cost_per_web_checkout: Optional[float] = None
    # ── CPAS "Shared Item" (catalog-segment) events + cost-per-step + ROAS ──
    purchase_shared: Optional[int] = None
    add_to_cart_shared: Optional[int] = None
    content_view_shared: Optional[int] = None
    purchase_value_shared: Optional[float] = None
    add_to_cart_value_shared: Optional[float] = None
    cost_per_purchase_shared: Optional[float] = None
    cost_per_add_to_cart_shared: Optional[float] = None
    cost_per_content_view_shared: Optional[float] = None
    roas_shared: Optional[float] = None
    # ── TikTok engagement / interactive / LIVE counts ──
    total_engagement: Optional[int] = None
    product_clicks_ix: Optional[int] = None
    live_views_10s: Optional[int] = None
    live_product_clicks: Optional[int] = None


class TableRow(BaseModel):
    id: str
    name: str
    status: str
    effective_status: str
    platform: str
    metrics: TableMetrics
    # Present only when the request sets compare_previous=true. Same key set as
    # `metrics`; entities with no prior-window data get a metrics dict of nulls.
    metrics_previous: Optional[TableMetrics] = None
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
    reach: Optional[int] = None
    clicks: Optional[int] = None
    spend: Optional[float] = None
    conversions: Optional[float] = None
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


class PerAccountSummary(BaseModel):
    account_id: str
    name: str
    platform: Optional[str] = None
    currency: Optional[str] = None
    summary: MetricsSummary


class CombinedOverviewResponse(BaseModel):
    combined: bool
    currency_mismatch: bool
    currency: Optional[str] = None
    currencies: list[str] = []
    period: PeriodInfo
    summary: MetricsSummary
    vs_previous: dict[str, Optional[float]] = {}
    per_account: list[PerAccountSummary] = []
    account_count: int = 0
