from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid

from app.db.base import get_db
from app.models.application import Application, ApplicationStatus, ApplicationFollowup
from app.models.job import Job
from app.models.user import Permission
from app.core.deps import require_permission, get_current_user

router = APIRouter()


class ApprovalAction(BaseModel):
    action: str  # approve | reject
    rejection_reason: Optional[str] = None


@router.get("/")
async def list_applications(
    status: Optional[ApplicationStatus] = None,
    profile_id: Optional[uuid.UUID] = None,
    pinned_only: bool = False,
    page: int = 1,
    page_size: int = 50,
    current_user=Depends(require_permission(Permission.view_applications)),
    db: AsyncSession = Depends(get_db),
):
    query = select(Application)
    if status:
        query = query.where(Application.status == status)
    if profile_id:
        query = query.where(Application.profile_id == profile_id)
    if pinned_only:
        query = query.where(Application.is_pinned == True)
    query = query.order_by(Application.is_pinned.desc(), Application.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    apps = result.scalars().all()

    out = []
    for a in apps:
        followups_r = await db.execute(select(ApplicationFollowup).where(ApplicationFollowup.application_id == a.id).order_by(ApplicationFollowup.follow_up_number))
        out.append({
            "id": str(a.id),
            "job_id": str(a.job_id) if a.job_id else None,
            "profile_id": str(a.profile_id),
            "to_email": a.to_email,
            "to_name": a.to_name,
            "subject": a.subject,
            "body": a.body,
            "status": a.status,
            "is_pinned": a.is_pinned,
            "email_opened": a.email_opened,
            "opened_at": a.opened_at,
            "replied_at": a.replied_at,
            "scheduled_at": a.scheduled_at,
            "sent_at": a.sent_at,
            "follow_up_count": a.follow_up_count,
            "followups": [
                {
                    "id": str(f.id),
                    "number": f.follow_up_number,
                    "status": f.status,
                    "scheduled_at": f.scheduled_at,
                    "sent_at": f.sent_at,
                }
                for f in followups_r.scalars().all()
            ],
        })
    return out


@router.post("/{application_id}/approve")
async def approve_or_reject(
    application_id: uuid.UUID,
    data: ApprovalAction,
    current_user=Depends(require_permission(Permission.approve_applications)),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime
    result = await db.execute(select(Application).where(Application.id == application_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if data.action == "approve":
        app.status = ApplicationStatus.approved
        app.approved_by_id = current_user.id
        app.approved_at = datetime.utcnow()
        await db.commit()
        # Trigger send
        from app.tasks.applicator import send_application_task
        send_application_task.delay(str(application_id))
        return {"message": "Approved and queued for sending"}
    elif data.action == "reject":
        app.status = ApplicationStatus.rejected
        app.rejection_reason = data.rejection_reason
        await db.commit()
        return {"message": "Rejected"}
    else:
        raise HTTPException(status_code=400, detail="action must be approve or reject")


@router.patch("/{application_id}/pin")
async def toggle_pin(
    application_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_applications)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Application).where(Application.id == application_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.is_pinned = not app.is_pinned
    await db.commit()
    return {"is_pinned": app.is_pinned}


@router.get("/pending-approval")
async def pending_approval(
    current_user=Depends(require_permission(Permission.approve_applications)),
    db: AsyncSession = Depends(get_db),
):
    # Job application pending approvals
    result = await db.execute(
        select(Application).where(Application.status == ApplicationStatus.pending_approval).order_by(Application.created_at)
    )
    apps = result.scalars().all()
    items = [
        {
            "id": str(a.id),
            "type": "job",
            "to_email": a.to_email,
            "to_name": a.to_name,
            "subject": a.subject,
            "body": a.body,
            "profile_id": str(a.profile_id),
            "job_id": str(a.job_id) if a.job_id else None,
            "scheduled_at": a.scheduled_at,
            "created_at": a.created_at,
        }
        for a in apps
    ]

    # B2B lead pending approvals
    from app.models.lead import Lead, LeadStatus
    lead_result = await db.execute(
        select(Lead).where(Lead.status == LeadStatus.pending_approval).order_by(Lead.created_at)
    )
    leads = lead_result.scalars().all()
    for l in leads:
        breakdown = l.score_breakdown or {}
        items.append({
            "id": str(l.id),
            "type": "b2b",
            "to_email": l.contact_email,
            "to_name": l.contact_name,
            "subject": breakdown.get("_pending_subject", ""),
            "body": breakdown.get("_pending_body", ""),
            "company_name": l.company_name,
            "industry": l.industry,
            "country": l.country,
            "score": l.score,
            "scheduled_at": l.scheduled_at,
            "created_at": l.created_at,
        })

    return items
