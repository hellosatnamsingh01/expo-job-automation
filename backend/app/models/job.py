import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import Base


class JobActivityType(str, enum.Enum):
    contact_added = "contact_added"
    contact_updated = "contact_updated"
    status_changed = "status_changed"
    manually_applied = "manually_applied"


class JobStatus(str, enum.Enum):
    new = "new"
    matched = "matched"
    researching = "researching"
    ready = "ready"
    scheduled = "scheduled"
    applied = "applied"
    followed_up = "followed_up"
    replied = "replied"
    cold = "cold"
    blacklisted = "blacklisted"
    skipped = "skipped"
    bounced = "bounced"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platforms.id"), nullable=True)

    # Core job info
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=True)
    company_linkedin_url: Mapped[str] = mapped_column(String(500), nullable=True)
    company_size: Mapped[str] = mapped_column(String(100), nullable=True)
    company_website: Mapped[str] = mapped_column(String(500), nullable=True)
    industry: Mapped[str] = mapped_column(String(100), nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), nullable=True)
    job_url: Mapped[str] = mapped_column(String(500), nullable=True)
    apply_url: Mapped[str] = mapped_column(String(500), nullable=True)
    job_description: Mapped[str] = mapped_column(Text, nullable=True)

    # Skills extracted from JD
    required_skills: Mapped[list] = mapped_column(JSON, nullable=True)

    # Matched profile
    matched_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=True)

    # Status
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus), default=JobStatus.new)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    has_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Research retry counter — skip after 3 failed attempts
    research_attempts: Mapped[int] = mapped_column(Integer, default=0)

    # Dedup hash
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=True, index=True)

    # Source
    posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    uploaded_manually: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    platform: Mapped["Platform"] = relationship("Platform", back_populates="jobs")
    matched_profile: Mapped["Profile"] = relationship("Profile")
    contacts: Mapped[list["JobContact"]] = relationship("JobContact", back_populates="job", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="job")


class JobContact(Base):
    """Hiring persons / contacts for a job."""
    __tablename__ = "job_contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str] = mapped_column(String(500), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(100), nullable=True)  # jd_email, apollo, luca, manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="contacts")


class JobActivity(Base):
    """Tracks who updated job contacts/status — used for researcher/role stats."""
    __tablename__ = "job_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_name: Mapped[str] = mapped_column(String(255), nullable=True)
    user_role: Mapped[str] = mapped_column(String(100), nullable=True)
    activity_type: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
