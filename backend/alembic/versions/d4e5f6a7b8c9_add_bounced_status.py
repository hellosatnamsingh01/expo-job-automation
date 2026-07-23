"""add bounced to application and job status enums

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-21
"""
from alembic import op

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'bounced'")
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'bounced'")


def downgrade():
    # Postgres does not support removing enum values; downgrade is a no-op
    pass
