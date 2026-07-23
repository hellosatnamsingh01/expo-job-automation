from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from app.db.base import get_db
from app.models.application import Application, ApplicationStatus
from app.models.lead import Lead, LeadStatus
from app.models.job import Job
from app.models.user import Permission
from app.core.deps import require_permission

router = APIRouter()


@router.get("/overview")
async def overview(
    current_user=Depends(require_permission(Permission.view_analytics)),
    db: AsyncSession = Depends(get_db),
):
    # Jobs stats
    total_jobs = (await db.execute(select(func.count(Job.id)))).scalar()
    jobs_applied = (await db.execute(select(func.count(Application.id)).where(Application.status.in_([ApplicationStatus.sent, ApplicationStatus.opened, ApplicationStatus.replied])))).scalar()
    apps_opened = (await db.execute(select(func.count(Application.id)).where(Application.email_opened == True))).scalar()
    apps_replied = (await db.execute(select(func.count(Application.id)).where(Application.replied_at.isnot(None)))).scalar()
    apps_pending = (await db.execute(select(func.count(Application.id)).where(Application.status == ApplicationStatus.pending_approval))).scalar()

    # Leads stats
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar()
    leads_sent = (await db.execute(select(func.count(Lead.id)).where(Lead.sent_at.isnot(None)))).scalar()
    leads_opened = (await db.execute(select(func.count(Lead.id)).where(Lead.email_opened == True))).scalar()
    leads_replied = (await db.execute(select(func.count(Lead.id)).where(Lead.replied_at.isnot(None)))).scalar()
    leads_pending = (await db.execute(select(func.count(Lead.id)).where(Lead.status == LeadStatus.pending_approval))).scalar()

    return {
        "jobs": {
            "total": total_jobs,
            "applied": jobs_applied,
            "pending_approval": apps_pending,
            "opened": apps_opened,
            "replied": apps_replied,
            "open_rate": round(apps_opened / jobs_applied * 100, 1) if jobs_applied else 0,
            "reply_rate": round(apps_replied / jobs_applied * 100, 1) if jobs_applied else 0,
        },
        "b2b": {
            "total_leads": total_leads,
            "sent": leads_sent,
            "pending_approval": leads_pending,
            "opened": leads_opened,
            "replied": leads_replied,
            "open_rate": round(leads_opened / leads_sent * 100, 1) if leads_sent else 0,
            "reply_rate": round(leads_replied / leads_sent * 100, 1) if leads_sent else 0,
        },
    }


@router.get("/by-profile")
async def by_profile(
    current_user=Depends(require_permission(Permission.view_analytics)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            Application.profile_id,
            func.count(Application.id).label("total"),
            func.sum(case((Application.email_opened == True, 1), else_=0)).label("opened"),
            func.sum(case((Application.replied_at.isnot(None), 1), else_=0)).label("replied"),
        ).group_by(Application.profile_id)
    )
    rows = result.all()
    return [
        {
            "profile_id": str(r.profile_id),
            "total": r.total,
            "opened": r.opened,
            "replied": r.replied,
            "open_rate": round(r.opened / r.total * 100, 1) if r.total else 0,
            "reply_rate": round(r.replied / r.total * 100, 1) if r.total else 0,
        }
        for r in rows
    ]


@router.get("/by-country")
async def by_country(
    current_user=Depends(require_permission(Permission.view_analytics)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            Job.country,
            func.count(Application.id).label("applications"),
            func.sum(case((Application.replied_at.isnot(None), 1), else_=0)).label("replies"),
        )
        .join(Application, Application.job_id == Job.id)
        .group_by(Job.country)
        .order_by(func.count(Application.id).desc())
    )
    return [
        {"country": r.country, "applications": r.applications, "replies": r.replies}
        for r in result.all()
    ]
