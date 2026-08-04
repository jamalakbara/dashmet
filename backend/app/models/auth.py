import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Boolean, DateTime, Text, ForeignKey,
    UniqueConstraint, CheckConstraint, Index, func, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        Index("ix_organizations_slug", "slug"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    email_verify_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_password_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_password_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="user", foreign_keys="OrganizationMembership.user_id"
    )


class OrganizationMembership(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        CheckConstraint("role IN ('owner', 'member')", name="ck_membership_role"),
        Index("ix_membership_org_id", "organization_id"),
        Index("ix_membership_user_id", "user_id"),
        Index("ix_membership_invite_token", "invite_token"),
        # One pending invite per email per org — prevents duplicate pending rows
        # when the invited email has no user account yet (user_id is NULL).
        Index(
            "uq_membership_org_invite_email",
            "organization_id",
            "invite_email",
            unique=True,
            postgresql_where=text("invite_email IS NOT NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member")
    invited_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invite_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    invite_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    invite_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship(back_populates="memberships")
    user: Mapped[Optional["User"]] = relationship(
        back_populates="memberships", foreign_keys=[user_id]
    )
    account_grants: Mapped[list["MembershipAccount"]] = relationship(
        back_populates="membership", cascade="all, delete-orphan"
    )


class MembershipAccount(UUIDPrimaryKeyMixin, Base):
    """Per-member account allowlist. A row grants one membership access to one
    account. Owners are unrestricted (implicit access to every org account) and
    have no rows here; members see only the accounts granted to them. No row =
    no access. Cascades on both sides so removing a member or an account drops
    the grant automatically."""

    __tablename__ = "membership_accounts"
    __table_args__ = (
        UniqueConstraint("membership_id", "account_id", name="uq_membership_account"),
        Index("ix_membership_account_membership", "membership_id"),
        Index("ix_membership_account_account", "account_id"),
    )

    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    membership: Mapped["OrganizationMembership"] = relationship(
        back_populates="account_grants"
    )
