import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Enum as SAEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import Base


class TemplateType(str, enum.Enum):
    job_initial = "job_initial"
    job_followup_1 = "job_followup_1"
    job_followup_2 = "job_followup_2"
    job_followup_3 = "job_followup_3"
    b2b_initial = "b2b_initial"
    b2b_followup_1 = "b2b_followup_1"
    b2b_followup_2 = "b2b_followup_2"
    b2b_followup_3 = "b2b_followup_3"


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[TemplateType] = mapped_column(SAEnum(TemplateType), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional industry scope — NULL means generic (fallback for all industries)
    industry: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # A/B test version
    ab_version: Mapped[str] = mapped_column(String(1), nullable=True)  # 'A' or 'B'
    ab_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Stats
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
