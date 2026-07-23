from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional
import uuid
from app.db.base import get_db
from app.models.application import Application, ApplicationFollowup
from app.models.job import Job
from app.models.profile import Profile
from app.models.user import Permission
from app.core.deps import require_permission

router = APIRouter()


@router.get("/")
async def list_activities(
    limit: int = 100,
    job_id: Optional[uuid.UUID] = None,
    current_user=Depends(require_permission(Permission.view_applications)),
    db: AsyncSession = Depends(get_db),
):
    """Merged timeline of all application emails + follow-ups, newest first."""
    events = []

    # Applications
    query = select(Application).order_by(desc(Application.created_at)).limit(limit)
    if job_id:
        query = select(Application).where(Application.job_id == job_id).order_by(desc(Application.created_at))
    apps_r = await db.execute(query)
    apps = apps_r.scalars().all()

    for a in apps:
        job_title, company_name = None, None
        if a.job_id:
            j_r = await db.execute(select(Job).where(Job.id == a.job_id))
            j = j_r.scalar_one_or_none()
            if j:
                job_title = j.title
                company_name = j.company_name

        profile_name = None
        if a.profile_id:
            p_r = await db.execute(select(Profile).where(Profile.id == a.profile_id))
            p = p_r.scalar_one_or_none()
            if p:
                profile_name = p.name

        events.append({
            "id": str(a.id),
            "type": "application",
            "status": a.status,
            "job_id": str(a.job_id) if a.job_id else None,
            "job_title": job_title,
            "company_name": company_name,
            "profile_name": profile_name,
            "to_email": a.to_email,
            "to_name": a.to_name,
            "subject": a.subject,
            "body": a.body,
            "email_opened": a.email_opened,
            "opened_at": a.opened_at,
            "replied_at": a.replied_at,
            "sent_at": a.sent_at,
            "scheduled_at": a.scheduled_at,
            "created_at": a.created_at,
        })

        # Follow-ups under each application
        fus_r = await db.execute(
            select(ApplicationFollowup)
            .where(ApplicationFollowup.application_id == a.id)
            .order_by(ApplicationFollowup.follow_up_number)
        )
        for fu in fus_r.scalars().all():
            events.append({
                "id": str(fu.id),
                "type": "followup",
                "followup_number": fu.follow_up_number,
                "status": fu.status,
                "job_id": str(a.job_id) if a.job_id else None,
                "job_title": job_title,
                "company_name": company_name,
                "profile_name": profile_name,
                "to_email": a.to_email,
                "to_name": a.to_name,
                "subject": fu.subject,
                "sent_at": fu.sent_at,
                "scheduled_at": fu.scheduled_at,
                "created_at": fu.scheduled_at or a.created_at,
            })

    # Sort all events by created_at desc
    events.sort(key=lambda e: e["created_at"] or e.get("sent_at") or "", reverse=True)
    return events
