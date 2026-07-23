import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import Base


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    manager = "manager"
    outreach_specialist = "outreach_specialist"
    researcher = "researcher"


class Permission(str, enum.Enum):
    # User management
    manage_users = "manage_users"
    manage_roles = "manage_roles"
    # Profile management
    manage_profiles = "manage_profiles"
    view_profiles = "view_profiles"
    # Platform management
    manage_platforms = "manage_platforms"
    view_platforms = "view_platforms"
    # Job management
    manage_jobs = "manage_jobs"
    view_jobs = "view_jobs"
    upload_jobs = "upload_jobs"
    # Applications
    manage_applications = "manage_applications"
    approve_applications = "approve_applications"
    view_applications = "view_applications"
    # B2B Leads
    manage_leads = "manage_leads"
    approve_leads = "approve_leads"
    view_leads = "view_leads"
    upload_leads = "upload_leads"
    # Email templates
    manage_templates = "manage_templates"
    # Settings
    manage_settings = "manage_settings"
    # Analytics
    view_analytics = "view_analytics"


ROLE_DEFAULT_PERMISSIONS = {
    UserRole.super_admin: list(Permission),
    UserRole.manager: [
        Permission.view_profiles,
        Permission.manage_platforms,
        Permission.view_platforms,
        Permission.view_jobs,
        Permission.upload_jobs,
        Permission.manage_applications,
        Permission.approve_applications,
        Permission.view_applications,
        Permission.approve_leads,
        Permission.view_leads,
        Permission.upload_leads,
        Permission.manage_templates,
        Permission.view_analytics,
    ],
    UserRole.outreach_specialist: [
        Permission.view_profiles,
        Permission.view_platforms,
        Permission.view_jobs,
        Permission.manage_applications,
        Permission.view_applications,
        Permission.manage_leads,
        Permission.view_leads,
        Permission.view_analytics,
    ],
    UserRole.researcher: [
        Permission.view_profiles,
        Permission.view_platforms,
        Permission.manage_jobs,
        Permission.view_jobs,
        Permission.upload_jobs,
        Permission.view_applications,
        Permission.upload_leads,
        Permission.view_leads,
    ],
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False, default=UserRole.researcher)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    permissions: Mapped[list["UserPermission"]] = relationship("UserPermission", back_populates="user", cascade="all, delete-orphan")
    email_accounts: Mapped[list["EmailAccount"]] = relationship("EmailAccount", back_populates="user")


class UserPermission(Base):
    """Per-user permission overrides — grants or revokes specific permissions regardless of role."""
    __tablename__ = "user_permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    permission: Mapped[Permission] = mapped_column(SAEnum(Permission), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)  # True = grant, False = revoke

    user: Mapped["User"] = relationship("User", back_populates="permissions")
