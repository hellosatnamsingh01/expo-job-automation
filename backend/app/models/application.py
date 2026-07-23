import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import Base


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
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
    bounced = "bounced"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("profiles.id"))
    profile_email_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("profile_emails.id"), nullable=True)

    # Sender (the email account that sent/will send this email)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=True)

    # Recipient
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    to_name: Mapped[str] = mapped_column(String(255), nullable=True)

    # Email content
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cv_path: Mapped[str] = mapped_column(String(500), nullable=True)  # path to generated PDF

    # Status
    status: Mapped[ApplicationStatus] = mapped_column(SAEnum(ApplicationStatus), default=ApplicationStatus.draft)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
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
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)

    # Gmail message id for threading
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship("Job", back_populates="applications")
    profile: Mapped["Profile"] = relationship("Profile", back_populates="applications")
    profile_email: Mapped["ProfileEmail"] = relationship("ProfileEmail")
    followups: Mapped[list["ApplicationFollowup"]] = relationship("ApplicationFollowup", back_populates="application", cascade="all, delete-orphan")


class ApplicationFollowup(Base):
    __tablename__ = "application_followups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"))
    follow_up_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, sent, cancelled
    tracking_id: Mapped[str] = mapped_column(String(64), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    application: Mapped["Application"] = relationship("Application", back_populates="followups")
