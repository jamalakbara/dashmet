"""add_refresh_token_to_platform_connections

Revision ID: a1b2c3d4e5f6
Revises: seed_platforms_001
Create Date: 2026-06-01

Adds refresh_token and token_expires_at to platform_connections.
Required for TikTok OAuth tokens (24h access + 1y refresh lifecycle).
Meta connections leave both columns NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "seed_platforms_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_connections",
        sa.Column("refresh_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "platform_connections",
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_connections", "token_expires_at")
    op.drop_column("platform_connections", "refresh_token")
