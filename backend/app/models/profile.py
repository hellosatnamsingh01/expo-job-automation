import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import Base


class SkillType(str, enum.Enum):
    primary = "primary"
    secondary = "secondary"


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)  # display email
    bio: Mapped[str] = mapped_column(Text, nullable=True)
    years_experience: Mapped[int] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    skills: Mapped[list["ProfileSkill"]] = relationship("ProfileSkill", back_populates="profile", cascade="all, delete-orphan")
    cvs: Mapped[list["ProfileCV"]] = relationship("ProfileCV", back_populates="profile", cascade="all, delete-orphan")
    email_accounts: Mapped[list["ProfileEmail"]] = relationship("ProfileEmail", back_populates="profile", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="profile")


class ProfileSkill(Base):
    __tablename__ = "profile_skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"))
    skill: Mapped[str] = mapped_column(String(100), nullable=False)
    skill_type: Mapped[SkillType] = mapped_column(SAEnum(SkillType), nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="skills")


class ProfileCV(Base):
    __tablename__ = "profile_cvs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # path to Word file
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    region: Mapped[str | None] = mapped_column(String(20), nullable=True)  # e.g. US, CA, UK, AU, AE, OTHER, or None (default)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="cvs")


class ProfileEmail(Base):
    __tablename__ = "profile_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    gmail_token: Mapped[str] = mapped_column(Text, nullable=True)  # stored OAuth token JSON

    profile: Mapped["Profile"] = relationship("Profile", back_populates="email_accounts")
