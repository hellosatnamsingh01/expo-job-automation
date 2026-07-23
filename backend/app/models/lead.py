import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum, Float, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import Base


class LeadStatus(str, enum.Enum):
    new = "new"
    pending_approval = "pending_approval"
    approved = "approved"
    scheduled = "scheduled"
    sending = "sending"
    sent = "sent"
    failed = "failed"
    opened = "opened"
    replied = "replied"
    follow_up_1 = "follow_up_1"
    follow_up_2 = "follow_up_2"
    follow_up_3 = "follow_up_3"
    cold = "cold"
    # CRM pipeline
    interested = "interested"
    meeting_scheduled = "meeting_scheduled"
    proposal_sent = "proposal_sent"
    won = "won"
    lost = "lost"
    disqualified = "disqualified"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Company info
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_website: Mapped[str] = mapped_column(String(500), nullable=True)
    company_linkedin: Mapped[str] = mapped_column(String(500), nullable=True)
    industry: Mapped[str] = mapped_column(String(255), nullable=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=True)
    type: Mapped[str] = mapped_column(String(100), nullable=True)  # startup, enterprise etc
    company_description: Mapped[str] = mapped_column(Text, nullable=True)

    # Contact info
    contact_name: Mapped[str] = mapped_column(String(255), nullable=True)
    contact_title: Mapped[str] = mapped_column(String(255), nullable=True)
    contact_linkedin: Mapped[str] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=True)

    # Scoring
    score: Mapped[float] = mapped_column(Float, nullable=True)
    score_breakdown: Mapped[dict] = mapped_column(JSON, nullable=True)

    # Source
    source: Mapped[str] = mapped_column(String(100), nullable=True)  # apollo, linkedin, vibe, luca, manual
    assigned_to_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    sender_email_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("email_accounts.id"), nullable=True)

    # Status
    status: Mapped[LeadStatus] = mapped_column(SAEnum(LeadStatus), default=LeadStatus.new)
    follow_up_count: Mapped[int] = mapped_column(Integer, default=0)

    # Tracking
    tracking_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    email_opened: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    replied_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Scheduling
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Approval
    approved_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Gmail
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    activities: Mapped[list["LeadActivity"]] = relationship("LeadActivity", back_populates="lead", cascade="all, delete-orphan")
    sender_email: Mapped["EmailAccount"] = relationship("EmailAccount")


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # created, email_scheduled, email_sent, opened, replied, follow_up_sent
    detail: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="activities")
