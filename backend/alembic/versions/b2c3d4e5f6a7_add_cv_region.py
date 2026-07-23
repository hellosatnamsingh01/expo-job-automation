"""add region to profile_cvs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'profile_cvs',
        sa.Column('region', sa.String(20), nullable=True)
    )


def downgrade():
    op.drop_column('profile_cvs', 'region')
