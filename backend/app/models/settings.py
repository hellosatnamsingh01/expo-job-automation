import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Default settings keys:
# approval_enabled_jobs: true/false
# approval_enabled_b2b: true/false
# excluded_countries: JSON list
# followup_days: JSON [2, 4, 6]
# send_time_start: "09:00"
# send_time_end: "11:00"
# blacklisted_companies: JSON list
