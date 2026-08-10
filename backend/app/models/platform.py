import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Boolean, Text, ForeignKey,
    UniqueConstraint, Index, DateTime, func, ARRAY
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency_field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    timezone_field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class PlatformConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_connections"
    __table_args__ = (
        Index("ix_connections_org_id", "organization_id"),
        Index("ix_connections_platform_id", "platform_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    platform_id: Mapped[str] = mapped_column(
        ForeignKey("platforms.id"), nullable=False
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(50), nullable=False, default="system_user")
    scopes: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    connected_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Connection health — health status is derived from token_expires_at +
    # last_error (no separate enum column). Populated by worker sync/refresh
    # paths on failure; cleared/ignored when the connection recovers.
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    platform: Mapped["Platform"] = relationship()
    connected_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[connected_by_user_id]
    )
    accounts: Mapped[list["Account"]] = relationship(back_populates="connection")


class Account(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "platform_id", "external_id",
            name="uq_account_org_platform_external"
        ),
        Index("ix_accounts_org_id", "organization_id"),
        Index("ix_accounts_platform_connection_id", "platform_connection_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    platform_connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"), nullable=False
    )
    platform_id: Mapped[str] = mapped_column(
        ForeignKey("platforms.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    timezone: Mapped[str] = mapped_column(
        String(100), nullable=False, default="UTC"
    )
    account_status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="standard")
    business_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    business_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    connection: Mapped["PlatformConnection"] = relationship(back_populates="accounts")
    config: Mapped[Optional["AccountConfig"]] = relationship(
        back_populates="account", uselist=False
    )


class AccountConfig(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "account_configs"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_account_config_account"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    primary_conversion_action: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default="purchase"
    )
    attribution_window: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default="7d_click_1d_view"
    )
    roas_action_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default="purchase"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    account: Mapped["Account"] = relationship(back_populates="config")
