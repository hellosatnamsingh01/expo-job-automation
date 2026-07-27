import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AlertType(str, enum.Enum):
    key_exhausted   = "key_exhausted"    # API key ran out of credits
    key_rotated     = "key_rotated"      # Rotated to next key
    key_renewed     = "key_renewed"      # API key credits renewed and confirmed active
    key_error       = "key_error"        # Key returning unexpected error
    platform_error  = "platform_error"   # Platform scrape failed
    platform_ok     = "platform_ok"      # Platform scrape succeeded (info)
    email_disconnected = "email_disconnected"  # Gmail token expired/revoked
    email_error     = "email_error"      # Failed to send email
    reply_received  = "reply_received"   # Someone replied to a job application
    b2b_reply       = "b2b_reply"        # Someone replied to a B2B email
    lead_imported   = "lead_imported"    # Batch of leads imported
    enrich_done     = "enrich_done"      # Lead enrichment batch complete
    system          = "system"           # Generic system event


class AlertSeverity(str, enum.Enum):
    info    = "info"
    warning = "warning"
    error   = "error"


class SystemAlert(Base):
    __tablename__ = "system_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    type: Mapped[AlertType] = mapped_column(SAEnum(AlertType), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(SAEnum(AlertSeverity), nullable=False, default=AlertSeverity.info)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=True)   # e.g. "Indeed", "Gmail", "B2B"
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
