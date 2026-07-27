"""add key_renewed alert type

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-27 10:00:00.000000

"""
from alembic import op

revision: str = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE alerttype ADD VALUE IF NOT EXISTS 'key_renewed'")


def downgrade() -> None:
    pass  # Postgres does not support removing enum values
