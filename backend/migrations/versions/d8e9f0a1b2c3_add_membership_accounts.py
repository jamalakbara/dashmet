"""add membership_accounts (per-member account allowlist)

Grants a membership access to specific accounts. Owners are unrestricted and
have no rows here; members see only granted accounts (no row = no access). No
data backfill — existing members start with no access until an owner grants.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'membership_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('membership_id', sa.UUID(), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['membership_id'], ['organization_memberships.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['account_id'], ['accounts.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'membership_id', 'account_id', name='uq_membership_account'
        ),
    )
    op.create_index(
        'ix_membership_account_membership', 'membership_accounts', ['membership_id']
    )
    op.create_index(
        'ix_membership_account_account', 'membership_accounts', ['account_id']
    )


def downgrade() -> None:
    op.drop_index('ix_membership_account_account', table_name='membership_accounts')
    op.drop_index('ix_membership_account_membership', table_name='membership_accounts')
    op.drop_table('membership_accounts')
