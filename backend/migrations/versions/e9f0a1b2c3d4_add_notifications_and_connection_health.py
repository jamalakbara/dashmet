"""add notifications table + connection health columns

Adds the notifications table for token-expiry / sync-failure alerting, with a
composite UNIQUE (organization_id, dedup_key) as the DB-level dedup mechanism
(anti-req: dedup is a DB unique constraint, not an app-side time window) and a
(organization_id, status) index for the tenant-scoped unread-count query.

Also adds last_error / last_error_at to platform_connections for connection
health (status derived from token_expires_at + last_error, no enum column).

No data backfill — new table starts empty; the two new connection columns are
nullable and default NULL for existing rows.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('deep_link', sa.String(length=500), nullable=True),
        sa.Column('dedup_key', sa.String(length=255), nullable=False),
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='unread',
            nullable=False,
        ),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['organization_id'], ['organizations.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'dedup_key', name='uq_notifications_org_dedup'
        ),
    )
    op.create_index(
        'ix_notifications_org_status',
        'notifications',
        ['organization_id', 'status'],
    )

    op.add_column(
        'platform_connections',
        sa.Column('last_error', sa.Text(), nullable=True),
    )
    op.add_column(
        'platform_connections',
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('platform_connections', 'last_error_at')
    op.drop_column('platform_connections', 'last_error')

    op.drop_index('ix_notifications_org_status', table_name='notifications')
    op.drop_table('notifications')
