from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid, io
import pandas as pd

from app.db.base import get_db
from app.models.lead import Lead, LeadStatus, LeadActivity
from app.models.user import Permission
from app.core.deps import require_permission, get_current_user

router = APIRouter()


class LeadCreate(BaseModel):
    company_name: str
    company_website: Optional[str] = None
    company_linkedin: Optional[str] = None
    industry: Optional[str] = None
    domain: Optional[str] = None
    company_size: Optional[str] = None
    country: Optional[str] = None
    type: Optional[str] = None
    company_description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_linkedin: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    source: Optional[str] = "manual"
    sender_email_id: Optional[uuid.UUID] = None


class LeadUpdate(BaseModel):
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_linkedin: Optional[str] = None
    industry: Optional[str] = None
    domain: Optional[str] = None
    company_size: Optional[str] = None
    country: Optional[str] = None
    company_description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_linkedin: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    status: Optional[LeadStatus] = None
    score: Optional[float] = None
    sender_email_id: Optional[uuid.UUID] = None


class ApprovalAction(BaseModel):
    action: str  # approve | reject


def _lead_dict(l: Lead, sender_email: Optional[str] = None) -> dict:
    return {
        "id": str(l.id),
        "company_name": l.company_name,
        "company_website": l.company_website,
        "company_linkedin": l.company_linkedin,
        "domain": l.domain,
        "industry": l.industry,
        "company_size": l.company_size,
        "country": l.country,
        "company_description": l.company_description,
        "contact_name": l.contact_name,
        "contact_title": l.contact_title,
        "contact_linkedin": l.contact_linkedin,
        "contact_email": l.contact_email,
        "contact_phone": l.contact_phone,
        "status": l.status,
        "score": l.score,
        "source": l.source,
        "sender_email": sender_email,
        "sender_email_id": str(l.sender_email_id) if l.sender_email_id else None,
        "follow_up_count": l.follow_up_count,
        "email_opened": l.email_opened,
        "opened_at": l.opened_at,
        "replied_at": l.replied_at,
        "scheduled_at": l.scheduled_at,
        "sent_at": l.sent_at,
        "created_at": l.created_at,
    }


@router.get("/")
async def list_leads(
    status: Optional[LeadStatus] = None,
    country: Optional[str] = None,
    source: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    current_user=Depends(require_permission(Permission.view_leads)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    query = select(Lead).options(selectinload(Lead.sender_email))
    if status:
        query = query.where(Lead.status == status)
    if country:
        query = query.where(Lead.country == country)
    if source:
        query = query.where(Lead.source == source)
    query = query.order_by(Lead.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    leads = result.scalars().all()
    return [_lead_dict(l, l.sender_email.email if l.sender_email else None) for l in leads]


@router.get("/{lead_id}")
async def get_lead(
    lead_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.view_leads)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(Lead).options(selectinload(Lead.sender_email)).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _lead_dict(lead, lead.sender_email.email if lead.sender_email else None)


@router.post("/")
async def create_lead(
    data: LeadCreate,
    current_user=Depends(require_permission(Permission.manage_leads)),
    db: AsyncSession = Depends(get_db),
):
    lead = Lead(**data.model_dump(), assigned_to_id=current_user.id)
    db.add(lead)
    await db.flush()
    db.add(LeadActivity(lead_id=lead.id, action="created", detail=f"Created by {current_user.email}"))
    await db.commit()
    from app.tasks.scorer import score_lead_task
    score_lead_task.delay(str(lead.id))
    return {"id": str(lead.id), "message": "Lead created"}


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: uuid.UUID,
    data: LeadUpdate,
    current_user=Depends(require_permission(Permission.manage_leads)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(lead, field, value)
    db.add(LeadActivity(lead_id=lead.id, action="updated", detail=f"Updated by {current_user.email}"))
    await db.commit()
    return {"message": "Updated"}


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_leads)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.delete(lead)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/{lead_id}/approve")
async def approve_lead(
    lead_id: uuid.UUID,
    data: ApprovalAction,
    current_user=Depends(require_permission(Permission.approve_leads)),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if data.action == "approve":
        lead.status = LeadStatus.approved
        lead.approved_by_id = current_user.id
        lead.approved_at = datetime.utcnow()
        db.add(LeadActivity(lead_id=lead.id, action="approved", detail=f"Approved by {current_user.email}"))
        await db.commit()
        from app.tasks.outreach import send_b2b_email_task
        send_b2b_email_task.delay(str(lead_id))
        return {"message": "Approved and queued"}
    else:
        lead.status = LeadStatus.lost
        db.add(LeadActivity(lead_id=lead.id, action="rejected"))
        await db.commit()
        return {"message": "Rejected"}


@router.get("/{lead_id}/activities")
async def get_lead_activities(
    lead_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.view_leads)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LeadActivity).where(LeadActivity.lead_id == lead_id).order_by(LeadActivity.created_at)
    )
    return [
        {"action": a.action, "detail": a.detail, "created_at": a.created_at}
        for a in result.scalars().all()
    ]


@router.post("/upload")
async def upload_leads(
    file: UploadFile = File(...),
    current_user=Depends(require_permission(Permission.upload_leads)),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    created = 0
    for _, row in df.iterrows():
        company = str(row.get("company_name", row.get("Company", ""))).strip()
        if not company or company == "nan":
            continue
        lead = Lead(
            company_name=company,
            company_website=str(row.get("company_website", "")) or None,
            company_linkedin=str(row.get("company_linkedin", "")) or None,
            industry=str(row.get("industry", "")) or None,
            domain=str(row.get("domain", "")) or None,
            company_size=str(row.get("company_size", row.get("team_size", ""))) or None,
            country=str(row.get("country", "")) or None,
            company_description=str(row.get("company_description", row.get("description", ""))) or None,
            contact_name=str(row.get("contact_name", "")) or None,
            contact_title=str(row.get("contact_title", row.get("title", ""))) or None,
            contact_linkedin=str(row.get("contact_linkedin", "")) or None,
            contact_email=str(row.get("contact_email", row.get("email", ""))) or None,
            contact_phone=str(row.get("contact_phone", row.get("phone", ""))) or None,
            source=str(row.get("source", "upload")) or "upload",
            assigned_to_id=current_user.id,
        )
        db.add(lead)
        await db.flush()
        db.add(LeadActivity(lead_id=lead.id, action="created", detail="Uploaded via CSV"))
        created += 1

    await db.commit()
    return {"created": created}


@router.get("/scrape-status")
async def scrape_status(
    current_user=Depends(require_permission(Permission.manage_leads)),
    db: AsyncSession = Depends(get_db),
):
    """Return configured Apollo keys count and which index is currently active."""
    from app.tasks.b2b_leads import _get_apollo_keys_from_db
    from app.models.lead import Lead
    from sqlalchemy import func

    keys = _get_apollo_keys_from_db()
    from app.models.settings import GlobalSetting
    idx_row = await db.execute(
        select(GlobalSetting).where(GlobalSetting.key == "apollo_key_index")
    )
    idx_row = idx_row.scalar_one_or_none()
    current_idx = int(idx_row.value or 0) if idx_row else 0

    # Mask keys for display — show last 6 chars only
    masked = [f"...{k[-6:]}" for k in keys]

    total_result = await db.execute(select(func.count(Lead.id)))
    total_leads = total_result.scalar() or 0

    return {
        "apollo_keys_count": len(keys),
        "current_key_index": current_idx % len(keys) if keys else 0,
        "keys_preview": masked,
        "total_leads": total_leads,
    }


@router.post("/scrape")
async def scrape_leads(
    current_user=Depends(require_permission(Permission.manage_leads)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger Apollo and/or LinkedIn scraping. Returns which sources are active."""
    from app.tasks.b2b_leads import import_apollo_leads_task, import_linkedin_leads_task, _get_apollo_keys_from_db

    # Pre-flight: check which API keys are actually configured (DB first, then .env)
    apollo_keys = _get_apollo_keys_from_db()

    from app.api.v1.endpoints.settings import get_setting
    raw_apify = await get_setting(db, "apify_token") or ""
    apify_keys = [p.split("|")[-1].strip() for p in raw_apify.split(",") if p.strip() and "|" in p] or \
                 [p.strip() for p in raw_apify.split(",") if p.strip()]
    apify_keys = [k for k in apify_keys if k and "your-apify" not in k]
    apify_ok = bool(apify_keys)

    if not apollo_keys and not apify_ok:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_api_keys",
                "message": "No scraping API keys configured. Add your Apollo API key and/or Apify API key in Settings → API Keys.",
                "apollo": False,
                "apify": False,
            }
        )

    # Test Apollo key access level before queuing
    apollo_plan_ok = False
    if apollo_keys:
        import httpx as _httpx
        try:
            test = _httpx.post(
                "https://api.apollo.io/v1/mixed_people/search",
                json={"per_page": 1},
                headers={"X-Api-Key": apollo_keys[0]},
                timeout=10,
            )
            if test.status_code == 403 and test.json().get("error_code") == "API_INACCESSIBLE":
                if not apify_ok:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "apollo_plan_too_low",
                            "message": (
                                "Your Apollo API key is on a FREE plan which does not include people search (prospecting). "
                                "Upgrade your Apollo account at app.apollo.io to use B2B scraping."
                            ),
                            "apollo": False,
                            "apify": False,
                        }
                    )
                # Apollo free plan but Apify is configured — proceed with Apify only
            apollo_plan_ok = test.status_code in (200, 422)  # 422 means valid key but bad payload — that's fine
        except HTTPException:
            raise
        except Exception:
            apollo_plan_ok = True  # network error — try anyway

    sources = []
    if apollo_keys and apollo_plan_ok:
        import_apollo_leads_task.delay()
        sources.append("Apollo")
    if apify_ok:
        import_linkedin_leads_task.delay()
        sources.append("LinkedIn (Apify)")

    return {
        "message": f"Scraping started via: {', '.join(sources)}",
        "sources": sources,
        "apollo": bool(apollo_keys),
        "apify": apify_ok,
    }


@router.get("/export")
async def export_leads(
    current_user=Depends(require_permission(Permission.view_leads)),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    result = await db.execute(select(Lead).order_by(Lead.created_at.desc()))
    leads = result.scalars().all()
    rows = [
        {
            "Company": l.company_name,
            "Website": l.company_website,
            "LinkedIn": l.company_linkedin,
            "Industry": l.industry,
            "Team Size": l.company_size,
            "Country": l.country,
            "Description": l.company_description,
            "Contact": l.contact_name,
            "Title": l.contact_title,
            "Contact LinkedIn": l.contact_linkedin,
            "Email": l.contact_email,
            "Phone": l.contact_phone,
            "Score": l.score,
            "Status": l.status,
            "Source": l.source,
            "Scraped At": l.created_at,
            "Scheduled Send": l.scheduled_at,
            "Sent At": l.sent_at,
        }
        for l in leads
    ]
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=leads_export.xlsx"},
    )
