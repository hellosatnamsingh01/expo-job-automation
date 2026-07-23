"""widen cv region column to 20

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('profile_cvs', 'region', type_=sa.String(20), existing_nullable=True)


def downgrade():
    op.alter_column('profile_cvs', 'region', type_=sa.String(10), existing_nullable=True)
