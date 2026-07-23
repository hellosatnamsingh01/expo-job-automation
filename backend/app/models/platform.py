import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import Base


class ScrapeType(str, enum.Enum):
    indeed = "indeed"
    linkedin = "linkedin"
    weworkremotely = "weworkremotely"
    wellfound = "wellfound"
    remoteok = "remoteok"
    remotive = "remotive"
    shine = "shine"
    nauk = "nauk"
    bark = "bark"
    custom = "custom"
    manual = "manual"


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    scrape_type: Mapped[ScrapeType] = mapped_column(SAEnum(ScrapeType), nullable=False, default=ScrapeType.custom)
    scrape_config: Mapped[dict] = mapped_column(JSON, nullable=True)  # field selectors, pagination config
    keywords: Mapped[str] = mapped_column(Text, nullable=True)  # comma separated alert keywords
    scrape_frequency_hours: Mapped[int] = mapped_column(Integer, default=24)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_scraped_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="platform")
