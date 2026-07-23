from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base import AsyncSessionLocal
from app.models.application import Application, ApplicationFollowup
from app.models.lead import Lead, LeadActivity
import base64
from datetime import datetime

router = APIRouter()

# 1x1 transparent GIF
TRACKING_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@router.get("/pixel/{tracking_id}")
async def track_open(tracking_id: str, request: Request):
    async with AsyncSessionLocal() as db:
        # Check applications
        result = await db.execute(select(Application).where(Application.tracking_id == tracking_id))
        app = result.scalar_one_or_none()
        if app and not app.email_opened:
            app.email_opened = True
            app.opened_at = datetime.utcnow()
            if app.status in (ApplicationStatus.sent, ApplicationStatus.scheduled):
                app.status = ApplicationStatus.opened
            await db.commit()

        # Check followups
        result = await db.execute(select(ApplicationFollowup).where(ApplicationFollowup.tracking_id == tracking_id))
        followup = result.scalar_one_or_none()
        if followup and not followup.opened_at:
            followup.opened_at = datetime.utcnow()
            await db.commit()

        # Check leads
        result = await db.execute(select(Lead).where(Lead.tracking_id == tracking_id))
        lead = result.scalar_one_or_none()
        if lead and not lead.email_opened:
            lead.email_opened = True
            lead.opened_at = datetime.utcnow()
            db.add(LeadActivity(lead_id=lead.id, action="email_opened", detail="Email opened"))
            await db.commit()

    return Response(content=TRACKING_PIXEL, media_type="image/gif")
