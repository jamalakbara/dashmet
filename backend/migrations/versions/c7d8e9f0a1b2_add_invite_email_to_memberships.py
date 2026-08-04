"""add invite_email to organization_memberships

Stores the invited email on pending memberships (user_id is NULL until the
invite is accepted) so pending invites display the real address and can be
deduped/removed. Partial unique index enforces one pending invite per email
per org.

Revision ID: c7d8e9f0a1b2
Revises: f05a9fcb7e8d
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'f05a9fcb7e8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'organization_memberships',
        sa.Column('invite_email', sa.String(length=255), nullable=True),
    )
    op.create_index(
        'uq_membership_org_invite_email',
        'organization_memberships',
        ['organization_id', 'invite_email'],
        unique=True,
        postgresql_where=sa.text('invite_email IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_membership_org_invite_email',
        table_name='organization_memberships',
    )
    op.drop_column('organization_memberships', 'invite_email')
