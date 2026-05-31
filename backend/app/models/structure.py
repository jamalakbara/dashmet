import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    String, Numeric, ForeignKey, Date, DateTime,
    UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class Campaign(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "platform_campaign_id",
            name="uq_campaign_account_platform_id"
        ),
        Index("ix_campaigns_account_id", "account_id"),
        Index("ix_campaigns_platform_id", "platform_id"),
        Index("ix_campaigns_status", "status"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    platform_id: Mapped[str] = mapped_column(
        ForeignKey("platforms.id"), nullable=False
    )
    platform_campaign_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    effective_status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    objective: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    platform_objective: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    daily_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    lifetime_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    buying_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AdGroup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ad_groups"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "platform_adgroup_id",
            name="uq_adgroup_account_platform_id"
        ),
        Index("ix_adgroups_account_id", "account_id"),
        Index("ix_adgroups_campaign_id", "campaign_id"),
        Index("ix_adgroups_status", "status"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    platform_id: Mapped[str] = mapped_column(
        ForeignKey("platforms.id"), nullable=False
    )
    platform_adgroup_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    effective_status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    optimization_goal: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    billing_event: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bid_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    daily_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    lifetime_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    targeting_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Creative(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "creatives"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "platform_creative_id",
            name="uq_creative_account_platform_id"
        ),
        Index("ix_creatives_account_id", "account_id"),
        Index("ix_creatives_platform_creative_id", "platform_creative_id"),
    )

    platform_id: Mapped[str] = mapped_column(
        ForeignKey("platforms.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    platform_creative_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    body: Mapped[Optional[str]] = mapped_column(String(5000), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    video_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cta_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    destination_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    raw_spec: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Ad(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ads"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "platform_ad_id",
            name="uq_ad_account_platform_id"
        ),
        Index("ix_ads_account_id", "account_id"),
        Index("ix_ads_ad_group_id", "ad_group_id"),
        Index("ix_ads_campaign_id", "campaign_id"),
        Index("ix_ads_status", "status"),
    )

    ad_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ad_groups.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    platform_id: Mapped[str] = mapped_column(
        ForeignKey("platforms.id"), nullable=False
    )
    platform_ad_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    effective_status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    creative_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("creatives.id", ondelete="SET NULL"), nullable=True
    )
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    creative: Mapped[Optional["Creative"]] = relationship()
