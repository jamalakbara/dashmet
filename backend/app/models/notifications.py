import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Text, ForeignKey, UniqueConstraint, Index, DateTime, func
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # DB-level dedup (anti-req: dedup is a DB unique constraint, never an
        # app-side time window). Emission upserts ON CONFLICT DO NOTHING.
        UniqueConstraint(
            "organization_id", "dedup_key", name="uq_notifications_org_dedup"
        ),
        # Tenant-scoped unread-count / list query.
        Index("ix_notifications_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Stored column — never inferred from message text (anti-req).
    deep_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unread", server_default="unread"
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
