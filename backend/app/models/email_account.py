import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class EmailAccount(Base):
    """Gmail accounts used for sending — linked to a user (B2B) or profile (job applications)."""
    __tablename__ = "email_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    gmail_token: Mapped[str] = mapped_column(Text, nullable=True)  # JSON OAuth token
    client_id: Mapped[str] = mapped_column(Text, nullable=True)
    client_secret: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    # purpose: "job_applications" | "b2b" | "both"
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, default="job_applications")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="email_accounts")
