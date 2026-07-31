import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    String, BigInteger, Numeric, Boolean, Integer, Text,
    ForeignKey, Date, DateTime, UniqueConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class MetricsDaily(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "metrics_daily"
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_id", "date",
            name="uq_metrics_daily_entity_date"
        ),
        Index("ix_metrics_daily_account_date", "account_id", "date"),
        Index("ix_metrics_daily_entity_date", "entity_id", "date"),
        Index("ix_metrics_daily_account_entity_type", "account_id", "entity_type"),
    )

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    platform_id: Mapped[str] = mapped_column(String(50), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # Core performance
    impressions: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reach: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    frequency: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    clicks: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    spend: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    ctr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    cpm: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    cpc: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    cpp: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Click detail
    unique_clicks: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    inline_link_clicks: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    unique_inline_link_clicks: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    inline_link_click_ctr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    unique_ctr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    cost_per_inline_link_click: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    cost_per_unique_click: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Engagement
    inline_post_engagement: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    cost_per_inline_post_engagement: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Auction diagnostic
    auction_bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    auction_competitiveness: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    auction_max_competitor_bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Aggregates
    total_actions: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    total_unique_actions: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    result_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)

    # Estimated / brand
    estimated_ad_recall_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    estimated_ad_recallers: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Sync metadata
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_estimated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    attribution_window: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class MetricActionStats(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "metric_action_stats"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "date", "field_name", "action_type",
            name="uq_action_stats_entity_date_field_action"
        ),
        Index("ix_action_stats_entity_date", "entity_id", "date"),
        Index(
            "ix_action_stats_account_date_field_action",
            "account_id", "date", "field_name", "action_type"
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    platform_id: Mapped[str] = mapped_column(String(50), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MetricBreakdowns(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "metric_breakdowns"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "date", "breakdown_type", "breakdown_value",
            name="uq_breakdowns_entity_date_type_value"
        ),
        Index("ix_breakdowns_entity_date", "entity_id", "date"),
        Index("ix_breakdowns_account_date", "account_id", "date"),
    )

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    platform_id: Mapped[str] = mapped_column(String(50), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    breakdown_type: Mapped[str] = mapped_column(String(50), nullable=False)
    breakdown_value: Mapped[str] = mapped_column(String(200), nullable=False)

    impressions: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reach: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    clicks: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    spend: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    conversions: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    ctr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    cpm: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    cpc: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncJob(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index("ix_sync_jobs_account_type_status", "account_id", "job_type", "status"),
        Index("ix_sync_jobs_type_status_platform_job", "job_type", "status", "platform_job_id"),
        Index("ix_sync_jobs_created_at", "created_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    platform_id: Mapped[str] = mapped_column(String(50), nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    date_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_stop: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    breakdown_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    platform_job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rows_written: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rate_limit_pct_at_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
