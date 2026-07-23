"""fix enum values and nullable profile_email_id

Revision ID: a1b2c3d4e5f6
Revises: 0b7194cb1068
Create Date: 2026-07-17 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0b7194cb1068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing enum values — must run outside a transaction in PostgreSQL
    conn = op.get_bind()

    # applicationstatus: add 'sending' and 'failed' if missing
    for val in ('sending', 'failed'):
        conn.execute(sa.text(
            f"DO $$ BEGIN "
            f"  IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = '{val}' "
            f"  AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'applicationstatus')) "
            f"  THEN ALTER TYPE applicationstatus ADD VALUE '{val}'; "
            f"  END IF; "
            f"END $$;"
        ))

    # jobstatus: add 'scheduled' if missing
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "  IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'scheduled' "
        "  AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'jobstatus')) "
        "  THEN ALTER TYPE jobstatus ADD VALUE 'scheduled'; "
        "  END IF; "
        "END $$;"
    ))

    # Make profile_email_id nullable — email can come from EmailAccount not ProfileEmail
    op.alter_column('applications', 'profile_email_id',
                    existing_type=sa.UUID(),
                    nullable=True)

    # Add research_attempts column if missing
    conn.execute(sa.text(
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS research_attempts INTEGER NOT NULL DEFAULT 0"
    ))

    # Add skipped_job_retention_days to global settings seed (idempotent)
    conn.execute(sa.text(
        "INSERT INTO global_settings (id, key, value, updated_at) "
        "VALUES (gen_random_uuid(), 'skipped_job_retention_days', '0', NOW()) "
        "ON CONFLICT (key) DO NOTHING"
    ))


def downgrade() -> None:
    op.alter_column('applications', 'profile_email_id',
                    existing_type=sa.UUID(),
                    nullable=False)
