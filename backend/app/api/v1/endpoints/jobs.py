from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from pydantic import BaseModel
from typing import Optional, List
import uuid, hashlib, json
import pandas as pd
import io

from app.db.base import get_db
from app.models.job import Job, JobContact, JobStatus, JobActivity, JobActivityType
from app.models.profile import Profile, ProfileEmail
from app.models.platform import Platform
from app.models.application import Application, ApplicationFollowup
from app.models.user import Permission
from app.core.deps import require_permission

router = APIRouter()


async def _log_job_activity(db: AsyncSession, job_id, user, activity_type: JobActivityType, detail: str = None):
    """Record a job activity entry for the given user."""
    db.add(JobActivity(
        job_id=job_id,
        user_id=user.id if user else None,
        user_name=getattr(user, "full_name", None) or getattr(user, "email", None),
        user_role=getattr(user, "role", None),
        activity_type=activity_type,
        detail=detail,
    ))


async def _auto_promote_job(db: AsyncSession, job: Job):
    """If job is still in researching and now has email+name, promote to ready and trigger apply.
    If status was manually set to anything other than researching, leave it untouched."""
    if job.status != JobStatus.researching:
        return  # manually set status — don't override

    contacts_r = await db.execute(select(JobContact).where(JobContact.job_id == job.id))
    contacts = contacts_r.scalars().all()
    primary = next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)

    if primary and primary.email and primary.name:
        job.status = JobStatus.ready
        await db.commit()
        from app.tasks.applicator import apply_job_task
        apply_job_task.delay(str(job.id))


class ContactIn(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    is_primary: bool = False
    source: Optional[str] = "manual"


class JobCreate(BaseModel):
    title: str
    company_name: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    job_url: Optional[str] = None
    apply_url: Optional[str] = None
    job_description: Optional[str] = None
    platform_id: Optional[uuid.UUID] = None
    contacts: List[ContactIn] = []


class JobUpdate(BaseModel):
    title: Optional[str] = None
    company_name: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    job_url: Optional[str] = None
    apply_url: Optional[str] = None
    job_description: Optional[str] = None
    company_size: Optional[str] = None
    company_website: Optional[str] = None
    status: Optional[JobStatus] = None
    is_pinned: Optional[bool] = None
    auto_apply_enabled: Optional[bool] = None
    matched_profile_id: Optional[uuid.UUID] = None
    contacts: Optional[List[ContactIn]] = None


def make_dedup_hash(title: str, company: str) -> str:
    key = f"{title.lower().strip()}|{(company or '').lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:64]


@router.get("/")
async def list_jobs(
    status: Optional[JobStatus] = None,
    profile_id: Optional[uuid.UUID] = None,
    pinned_only: bool = False,
    uploaded_manually: Optional[bool] = None,
    page: int = 1,
    page_size: int = 2000,
    current_user=Depends(require_permission(Permission.view_jobs)),
    db: AsyncSession = Depends(get_db),
):
    query = select(Job)
    if status:
        query = query.where(Job.status == status)
    if profile_id:
        query = query.where(Job.matched_profile_id == profile_id)
    if pinned_only:
        query = query.where(Job.is_pinned == True)
    if uploaded_manually is not None:
        query = query.where(Job.uploaded_manually == uploaded_manually)
    # Pinned + replied at top, then newest scraped first
    query = query.order_by(
        Job.is_pinned.desc(),
        Job.has_reply.desc(),
        Job.scraped_at.desc().nullslast(),
        Job.created_at.desc(),
    )
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    out = []
    for j in jobs:
        contacts_r = await db.execute(select(JobContact).where(JobContact.job_id == j.id))
        contacts = contacts_r.scalars().all()
        primary_contact = next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)
        contact_found_at = primary_contact.created_at.isoformat() if primary_contact and primary_contact.created_at else None

        # Profile
        profile_name = None
        profile_email = None
        if j.matched_profile_id:
            pr = await db.execute(select(Profile).where(Profile.id == j.matched_profile_id))
            profile = pr.scalar_one_or_none()
            if profile:
                profile_name = profile.name
                pe_r = await db.execute(select(ProfileEmail).where(ProfileEmail.profile_id == profile.id, ProfileEmail.is_primary == True))
                pe = pe_r.scalar_one_or_none()
                if pe:
                    profile_email = pe.email

        # Skills are stored on the job record by the matcher at scrape/match time
        matched_skills = j.required_skills or []

        # Platform
        platform_name = None
        if j.platform_id:
            plat_r = await db.execute(select(Platform).where(Platform.id == j.platform_id))
            plat = plat_r.scalar_one_or_none()
            if plat:
                platform_name = plat.name

        # Application data
        app_r = await db.execute(select(Application).where(Application.job_id == j.id).order_by(Application.created_at.desc()))
        app = app_r.scalars().first()
        date_applied = None
        followup_dates = []
        applied_from_email = profile_email
        cv_url = None
        scheduled_at = None
        application_status = None
        if app:
            date_applied = app.sent_at
            application_status = app.status
            # If not yet sent, surface the scheduled send time
            if not app.sent_at and app.scheduled_at:
                scheduled_at = app.scheduled_at
            if app.cv_path:
                from app.core.config import settings
                storage_root = settings.STORAGE_PATH.rstrip("/")
                if app.cv_path.startswith(storage_root):
                    relative = app.cv_path[len(storage_root):].lstrip("/")
                    cv_url = f"{settings.APP_URL}/storage/{relative}"
                else:
                    cv_url = None  # path outside storage (old temp files) — not serveable
            fu_r = await db.execute(select(ApplicationFollowup).where(ApplicationFollowup.application_id == app.id).order_by(ApplicationFollowup.follow_up_number))
            followup_dates = [
                {
                    "id": str(fu.id),
                    "number": fu.follow_up_number,
                    "scheduled_at": fu.scheduled_at.isoformat() if fu.scheduled_at else None,
                    "sent_at": fu.sent_at.isoformat() if fu.sent_at else None,
                    "status": fu.status,
                }
                for fu in fu_r.scalars().all()
            ]

        out.append({
            "id": str(j.id),
            "title": j.title,
            "company_name": j.company_name,
            "company_linkedin_url": j.company_linkedin_url,
            "company_website": j.company_website,
            "company_size": j.company_size,
            "industry": j.industry,
            "location": j.location,
            "country": j.country,
            "status": j.status,
            "is_pinned": j.is_pinned,
            "has_reply": j.has_reply,
            "auto_apply_enabled": j.auto_apply_enabled if j.auto_apply_enabled is not None else True,
            "uploaded_manually": j.uploaded_manually,
            "posted_at": j.posted_at,
            "scraped_at": j.scraped_at,
            "matched_profile_id": str(j.matched_profile_id) if j.matched_profile_id else None,
            "matched_profile": {"name": profile_name, "email": profile_email} if profile_name else None,
            "matched_skills": matched_skills,
            "platform_id": str(j.platform_id) if j.platform_id else None,
            "platform_name": platform_name or ("Manual Upload" if j.uploaded_manually else "Unknown"),
            "created_at": j.created_at,
            "date_applied": date_applied,
            "scheduled_at": scheduled_at,
            "application_status": application_status,
            "followup_dates": followup_dates,
            "applied_from_email": applied_from_email,
            "cv_url": cv_url,
            "job_url": j.job_url,
            "apply_url": j.apply_url,
            "job_description": j.job_description,
            "contact_found_at": contact_found_at,
            "hiring_person": primary_contact.name if primary_contact else None,
            "hiring_email": primary_contact.email if primary_contact else None,
            "hiring_phone": primary_contact.phone if primary_contact else None,
            "hiring_linkedin": primary_contact.linkedin_url if primary_contact else None,
            "contacts": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "email": c.email,
                    "phone": c.phone,
                    "linkedin_url": c.linkedin_url,
                    "is_primary": c.is_primary,
                    "source": c.source,
                }
                for c in contacts
            ],
        })
    return out


@router.post("/")
async def create_job(
    data: JobCreate,
    current_user=Depends(require_permission(Permission.manage_jobs)),
    db: AsyncSession = Depends(get_db),
):
    dedup = make_dedup_hash(data.title, data.company_name or "")
    existing = await db.execute(select(Job).where(Job.dedup_hash == dedup))
    if existing.scalar_one_or_none():
        return {"message": "Duplicate job skipped", "duplicate": True}

    job = Job(
        title=data.title,
        company_name=data.company_name,
        company_linkedin_url=data.company_linkedin_url,
        location=data.location,
        country=data.country,
        job_url=data.job_url,
        apply_url=data.apply_url,
        job_description=data.job_description,
        platform_id=data.platform_id,
        dedup_hash=dedup,
        uploaded_manually=True,
    )
    db.add(job)
    await db.flush()

    for c in data.contacts:
        db.add(JobContact(job_id=job.id, **c.model_dump()))

    await db.commit()
    # Trigger matching
    from app.tasks.matcher import match_job_task
    match_job_task.delay(str(job.id))
    return {"id": str(job.id), "message": "Job created"}


@router.patch("/{job_id}")
async def update_job(
    job_id: uuid.UUID,
    data: JobUpdate,
    current_user=Depends(require_permission(Permission.manage_jobs)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    update_data = data.model_dump(exclude_none=True)
    contacts_data = update_data.pop("contacts", None)

    for field, value in update_data.items():
        setattr(job, field, value)

    status_manually_set = "status" in update_data

    if contacts_data is not None:
        await db.execute(
            __import__("sqlalchemy").delete(JobContact).where(JobContact.job_id == job_id)
        )
        for c in contacts_data:
            db.add(JobContact(job_id=job_id, **c))
        contact_names = ", ".join(c.get("email", "") for c in contacts_data if c.get("email"))
        await _log_job_activity(db, job_id, current_user, JobActivityType.contact_updated,
                                f"Contact updated: {contact_names}")

    if status_manually_set:
        await _log_job_activity(db, job_id, current_user, JobActivityType.status_changed,
                                f"Status set to {update_data['status']}")

    await db.commit()

    # Auto-promote to ready if researcher filled in required contact info
    if contacts_data is not None and not status_manually_set:
        await _auto_promote_job(db, job)

    return {"message": "Updated"}


@router.delete("/bulk")
async def bulk_delete_jobs(
    job_ids: list[str],
    current_user=Depends(require_permission(Permission.manage_jobs)),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    for jid in job_ids:
        result = await db.execute(select(Job).where(Job.id == _uuid.UUID(jid)))
        job = result.scalar_one_or_none()
        if job:
            await db.delete(job)
    await db.commit()
    return {"message": f"Deleted {len(job_ids)} jobs"}


@router.delete("/{job_id}")
async def delete_job(
    job_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_jobs)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.delete(job)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/{job_id}/contacts")
async def add_contact(
    job_id: uuid.UUID,
    data: ContactIn,
    current_user=Depends(require_permission(Permission.manage_jobs)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Mark existing contacts as non-primary if this one is primary
    contact_data = data.model_dump(exclude_none=True)
    if contact_data.get("is_primary"):
        await db.execute(
            __import__("sqlalchemy").update(JobContact)
            .where(JobContact.job_id == job_id)
            .values(is_primary=False)
        )

    contact = JobContact(job_id=job_id, source="manual", **contact_data)
    db.add(contact)

    await _log_job_activity(db, job_id, current_user, JobActivityType.contact_added,
                            f"Added contact: {data.name or ''} <{data.email or ''}>")
    await db.commit()

    # Auto-promote job if required fields now present
    await _auto_promote_job(db, job)

    return {"message": "Contact added"}


@router.delete("/{job_id}/contacts/{contact_id}")
async def delete_contact(
    job_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_jobs)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(JobContact).where(JobContact.id == contact_id, JobContact.job_id == job_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/upload")
async def upload_jobs(
    file: UploadFile = File(...),
    current_user=Depends(require_permission(Permission.upload_jobs)),
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

    def _col(row, *keys):
        """Read first matching column (case-insensitive, handles NaN)."""
        for k in keys:
            val = row.get(k, "")
            if str(val).strip().lower() not in ("", "nan", "none"):
                return str(val).strip()
        return ""

    # Normalise column names: strip whitespace, deduplicate suffixes (.1, .2) by keeping first
    col_map = {}
    for col in df.columns:
        clean = str(col).strip()
        base = clean.split(".")[0].strip()  # remove pandas .1 .2 suffixes on dupes
        if base not in col_map:
            col_map[base] = clean
    df = df.rename(columns={v: k for k, v in col_map.items()})

    created, skipped = 0, 0
    for _, row in df.iterrows():
        title = _col(row, "Title", "title", "Role", "Job Title")
        company = _col(row, "Company", "company_name")
        if not title:
            continue

        dedup = make_dedup_hash(title, company)
        existing_r = await db.execute(select(Job).where(Job.dedup_hash == dedup))
        job = existing_r.scalar_one_or_none()

        industry     = _col(row, "Industry", "industry") or None
        website      = _col(row, "Company Website", "company_website", "Website") or None
        linkedin_url = _col(row, "Company LinkedIn", "company_linkedin_url") or None
        team_size    = _col(row, "Team Size", "company_size") or None
        location     = _col(row, "Location", "location") or None
        country      = _col(row, "Country", "country") or None
        job_url      = _col(row, "Job URL", "job_url") or None
        description  = _col(row, "Job Description", "job_description") or None
        skills_raw   = _col(row, "Skills", "required_skills")
        skills       = [s.strip() for s in skills_raw.split(",") if s.strip()] or None

        from datetime import datetime as _dt
        now = _dt.utcnow()

        if job:
            # Update fields that were blank on the first import
            if industry and not job.industry:           job.industry = industry
            if website and not job.company_website:     job.company_website = website
            if linkedin_url and not job.company_linkedin_url: job.company_linkedin_url = linkedin_url
            if team_size and not job.company_size:      job.company_size = team_size
            if location and not job.location:           job.location = location
            if country and not job.country:             job.country = country
            if job_url and not job.job_url:             job.job_url = job_url
            if description and not job.job_description: job.job_description = description
            if skills and not job.required_skills:      job.required_skills = skills
            job.scraped_at = now
            skipped += 1  # count as skipped (not a new row) but still update
        else:
            job = Job(
                title=title,
                company_name=company or None,
                industry=industry,
                company_website=website,
                company_linkedin_url=linkedin_url,
                company_size=team_size,
                location=location,
                country=country,
                job_url=job_url,
                job_description=description,
                required_skills=skills,
                dedup_hash=dedup,
                uploaded_manually=True,
                scraped_at=now,
            )
            db.add(job)
            created += 1

        await db.flush()

        # Contact — support both export format and raw columns
        email    = _col(row, "Email", "email")
        name     = _col(row, "Hiring Person", "hiring_person")
        title_str = _col(row, "Hiring Person Title", "hiring_person_title")
        linkedin = _col(row, "Hiring Person LinkedIn", "hiring_person_linkedin")
        if email:
            existing_contact_r = await db.execute(
                select(JobContact).where(JobContact.job_id == job.id, JobContact.is_primary == True)
            )
            contact = existing_contact_r.scalar_one_or_none()
            if contact:
                if email and not contact.email:           contact.email = email
                if name and not contact.name:             contact.name = name
                if title_str and not contact.title:       contact.title = title_str
                if linkedin and not contact.linkedin_url: contact.linkedin_url = linkedin
            else:
                db.add(JobContact(
                    job_id=job.id,
                    email=email,
                    name=name or None,
                    title=title_str or None,
                    linkedin_url=linkedin or None,
                    source="upload",
                    is_primary=True,
                ))

    await db.commit()

    # Trigger matching for newly uploaded jobs
    from app.tasks.matcher import match_all_unmatched_task
    match_all_unmatched_task.delay()

    return {"created": created, "updated": skipped}


class ExportJobsRequest(BaseModel):
    ids: Optional[list[str]] = None


@router.post("/export")
async def export_jobs(
    body: ExportJobsRequest = ExportJobsRequest(),
    current_user=Depends(require_permission(Permission.view_jobs)),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    import uuid as _uuid
    q = select(Job).order_by(Job.created_at.desc())
    if body.ids:
        q = q.where(Job.id.in_([_uuid.UUID(i) for i in body.ids]))
    result = await db.execute(q)
    jobs = result.scalars().all()

    rows = []
    for j in jobs:
        contacts_r = await db.execute(select(JobContact).where(JobContact.job_id == j.id, JobContact.is_primary == True))
        contact = contacts_r.scalar_one_or_none()
        # Resolve platform name
        platform_name = ""
        if j.platform_id:
            p_r = await db.execute(select(Platform).where(Platform.id == j.platform_id))
            p = p_r.scalar_one_or_none()
            platform_name = p.name if p else str(j.platform_id)

        # Resolve matched profile name
        profile_name = ""
        if j.matched_profile_id:
            from app.models.profile import Profile
            pr_r = await db.execute(select(Profile).where(Profile.id == j.matched_profile_id))
            pr = pr_r.scalar_one_or_none()
            profile_name = pr.name if pr else ""

        rows.append({
            "Title": j.title,
            "Company": j.company_name,
            "Industry": j.industry or "",
            "Company Website": j.company_website or "",
            "Company LinkedIn": j.company_linkedin_url or "",
            "Team Size": j.company_size or "",
            "Location": j.location or "",
            "Country": j.country or "",
            "Platform": platform_name,
            "Applied From (Profile)": profile_name,
            "Job URL": j.job_url or "",
            "Apply URL": j.apply_url or "",
            "Skills": ", ".join(j.required_skills) if j.required_skills else "",
            "Job Description": j.job_description or "",
            "Hiring Person": contact.name if contact else "",
            "Hiring Person Title": contact.title if contact else "",
            "Email": contact.email if contact else "",
            "Phone": contact.phone if contact else "",
            "Hiring Person LinkedIn": contact.linkedin_url if contact else "",
            "Status": j.status,
            "Manually Added": "Yes" if j.uploaded_manually else "No",
            "Scraped At": j.scraped_at,
            "Created At": j.created_at,
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=jobs_export.xlsx"},
    )


@router.post("/run-pipeline")
async def run_pipeline(
    current_user=Depends(require_permission(Permission.manage_applications)),
    db: AsyncSession = Depends(get_db),
):
    """Match all unmatched/new jobs to profiles and schedule them."""
    result = await db.execute(select(Job).where(
        Job.status.in_(["new", "researching", "ready", "matched"])
    ))
    jobs = result.scalars().all()
    triggered = []
    for job in jobs:
        from app.tasks.matcher import match_job_task
        match_job_task.delay(str(job.id))
        triggered.append(str(job.id))
    return {"message": f"Pipeline triggered for {len(triggered)} jobs", "job_ids": triggered}


@router.patch("/{job_id}/assign-profile")
async def assign_profile_to_job(
    job_id: uuid.UUID,
    body: dict,
    current_user=Depends(require_permission(Permission.view_jobs)),
    db: AsyncSession = Depends(get_db),
):
    """Manually assign a profile to a job. Available to all roles."""
    profile_id_str = body.get("profile_id")
    if not profile_id_str:
        raise HTTPException(status_code=400, detail="profile_id is required")
    try:
        profile_id = uuid.UUID(profile_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid profile_id")

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    pr = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = pr.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    job.matched_profile_id = profile_id
    if job.status in (JobStatus.new, JobStatus.researching):
        job.status = JobStatus.matched
    await db.commit()

    # Trigger apply_job_task to create the Application + auto-schedule it.
    # If an application already exists for this job+profile, apply_job_task will
    # detect the duplicate and exit cleanly without creating a second one.
    from app.tasks.applicator import apply_job_task
    apply_job_task.delay(str(job_id))

    return {"message": f"Profile '{profile.name}' assigned to job — schedule computing in background", "profile_id": str(profile_id)}


@router.patch("/{job_id}/reschedule")
async def reschedule_job(
    job_id: uuid.UUID,
    body: dict,
    current_user=Depends(require_permission(Permission.view_jobs)),
    db: AsyncSession = Depends(get_db),
):
    """Update the scheduled_at time on the pending application for this job."""
    from app.models.application import Application, ApplicationStatus
    import dateutil.parser as _dp

    new_time_str = body.get("scheduled_at")
    if not new_time_str:
        raise HTTPException(status_code=400, detail="scheduled_at is required (ISO 8601 UTC)")

    try:
        new_time = _dp.parse(new_time_str)
        # Strip timezone info and store as UTC-naive
        if new_time.tzinfo is not None:
            import pytz
            new_time = new_time.astimezone(pytz.UTC).replace(tzinfo=None)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    # Accept any unsent application — including failed (allows rescheduling after downtime)
    app_r = await db.execute(
        select(Application)
        .where(Application.job_id == job_id)
        .where(Application.sent_at.is_(None))
        .where(Application.status.in_([
            ApplicationStatus.scheduled,
            ApplicationStatus.pending_approval,
            ApplicationStatus.sending,
            ApplicationStatus.failed,
        ]))
        .order_by(Application.created_at.desc())
    )
    application = app_r.scalars().first()
    if not application:
        raise HTTPException(status_code=404, detail="No unsent application found for this job. Assign a profile first.")

    application.scheduled_at = new_time
    # Reset failed applications back to scheduled so the sender picks them up
    if application.status == ApplicationStatus.failed:
        application.status = ApplicationStatus.scheduled
        # Also fix the job status
        from app.models.job import Job, JobStatus
        job_r = await db.execute(select(Job).where(Job.id == job_id))
        job = job_r.scalars().first()
        if job:
            job.status = JobStatus.scheduled
    await db.commit()
    return {"message": "Schedule updated", "scheduled_at": new_time.isoformat() + "Z"}


@router.patch("/{job_id}/followup/{followup_id}/reschedule")
async def reschedule_followup(
    job_id: uuid.UUID,
    followup_id: uuid.UUID,
    body: dict,
    current_user=Depends(require_permission(Permission.view_jobs)),
    db: AsyncSession = Depends(get_db),
):
    """Update scheduled_at on a pending follow-up email."""
    import dateutil.parser as _dp

    new_time_str = body.get("scheduled_at")
    if not new_time_str:
        raise HTTPException(status_code=400, detail="scheduled_at is required")

    try:
        new_time = _dp.parse(new_time_str)
        if new_time.tzinfo is not None:
            import pytz
            new_time = new_time.astimezone(pytz.UTC).replace(tzinfo=None)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    # Verify the followup belongs to an application of this job
    app_r = await db.execute(
        select(Application).where(Application.job_id == job_id)
    )
    app_ids = [a.id for a in app_r.scalars().all()]
    if not app_ids:
        raise HTTPException(status_code=404, detail="No application found for this job")

    fu_r = await db.execute(
        select(ApplicationFollowup).where(
            ApplicationFollowup.id == followup_id,
            ApplicationFollowup.application_id.in_(app_ids),
            ApplicationFollowup.status == "pending",
        )
    )
    fu = fu_r.scalars().first()
    if not fu:
        raise HTTPException(status_code=404, detail="Follow-up not found or already sent")

    fu.scheduled_at = new_time
    await db.commit()
    return {"message": "Follow-up rescheduled", "scheduled_at": new_time.isoformat() + "Z"}


@router.post("/{job_id}/apply")
async def trigger_apply(
    job_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_applications)),
    db: AsyncSession = Depends(get_db),
):
    from app.tasks.applicator import apply_job_task
    apply_job_task.delay(str(job_id))
    return {"message": "Application job queued"}


@router.post("/{job_id}/apply-now")
async def apply_now(
    job_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_applications)),
    db: AsyncSession = Depends(get_db),
):
    """Synchronous apply: auto-select profile → AI email → tailor CV → send via Gmail."""
    import secrets as _secrets
    from datetime import datetime as _dt
    from app.models.job import JobContact, JobStatus
    from app.models.profile import Profile, ProfileSkill, ProfileCV, ProfileEmail
    from app.models.email_account import EmailAccount
    from app.models.application import Application, ApplicationStatus
    from app.services.ai_service import generate_job_email, modify_cv_for_job
    from app.services.cv_service import extract_cv_text, prepare_cv_for_job
    from app.services.gmail_service import send_email
    from sqlalchemy import text

    # 1. Load job
    job_r = await db.execute(select(Job).where(Job.id == job_id))
    job = job_r.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    # 2. Auto-select best profile (skill match)
    profiles_r = await db.execute(select(Profile).where(Profile.is_active == True))
    profiles = profiles_r.scalars().all()
    if not profiles:
        raise HTTPException(400, "No active profiles found. Create a profile first.")

    job_text = f"{job.title} {job.job_description or ''}".lower()
    best_profile, best_score = profiles[0], 0
    for profile in profiles:
        skills_r = await db.execute(
            text("SELECT skill FROM profile_skills WHERE profile_id = :pid")
            .bindparams(pid=profile.id)
        )
        skills = [r[0].lower() for r in skills_r.fetchall()]
        score = sum(1 for s in skills if s in job_text)
        if score > best_score:
            best_score, best_profile = score, profile

    profile = best_profile

    # 3. Get primary skills
    skills_r = await db.execute(
        text("SELECT skill FROM profile_skills WHERE profile_id = :pid AND skill_type = 'primary'")
        .bindparams(pid=profile.id)
    )
    primary_skills = [r[0] for r in skills_r.fetchall()]

    # 4. Resolve sending Gmail account
    sending_token_json = None
    sender_email = profile.email

    pe_r = await db.execute(select(ProfileEmail).where(
        ProfileEmail.profile_id == profile.id, ProfileEmail.is_primary == True
    ))
    pe = pe_r.scalar_one_or_none()
    if pe and pe.gmail_token:
        sending_token_json = pe.gmail_token
        sender_email = pe.email

    if not sending_token_json:
        ea_r = await db.execute(select(EmailAccount).where(
            EmailAccount.email == sender_email, EmailAccount.is_authorized == True
        ))
        ea = ea_r.scalar_one_or_none()
        if not ea:
            ea_r = await db.execute(select(EmailAccount).where(
                EmailAccount.is_authorized == True, EmailAccount.is_active == True
            ))
            ea = ea_r.scalars().first()
        if ea:
            sending_token_json = ea.gmail_token
            sender_email = ea.email

    if not sending_token_json:
        raise HTTPException(400, "No connected Gmail account found. Connect a Gmail account in Email Accounts first.")

    # 5. Get contact to email
    contacts_r = await db.execute(select(JobContact).where(JobContact.job_id == job.id))
    contacts = contacts_r.scalars().all()
    contact = next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)
    if not contact or not contact.email:
        raise HTTPException(400, "No contact email on this job. Add a contact with an email address first.")

    # Duplicate guard — prevent double-send if button clicked twice
    existing_r = await db.execute(
        select(Application).where(
            Application.job_id == job.id,
            Application.profile_id == profile.id,
        )
    )
    if existing_r.scalars().first():
        raise HTTPException(409, "An application has already been sent for this job.")

    # 6. Load CV
    cv_r = await db.execute(select(ProfileCV).where(
        ProfileCV.profile_id == profile.id, ProfileCV.is_active == True
    ))
    cv = cv_r.scalars().first()

    # 7. Generate AI email
    try:
        email_content = generate_job_email(
            job_title=job.title,
            company_name=job.company_name or "",
            job_description=job.job_description or "",
            profile_name=profile.name,
            profile_skills=primary_skills,
            template_subject="Application for {role} at {company}",
            template_body="Hi,\n\nI am interested in the {role} role and believe my skills in {skills} make me a strong fit.\n\nBest regards,\n{name}",
            hiring_person_name=contact.name,
        )
    except Exception as e:
        raise HTTPException(500, f"AI email generation failed: {e}")

    # 8. Tailor CV using AI
    cv_attach_path = None
    if cv:
        try:
            cv_text = extract_cv_text(cv.file_path)
            if cv_text.strip() and not cv.file_path.lower().endswith(".pdf"):
                updated_cv_text = modify_cv_for_job(cv_text, job.title, job.job_description or "", primary_skills)
                cv_attach_path = prepare_cv_for_job(cv.file_path, updated_cv_text)
            else:
                cv_attach_path = cv.file_path
        except Exception as e:
            print(f"[apply-now] CV tailor error: {e}")
            cv_attach_path = cv.file_path

    # 9. Send email
    tracking_id = _secrets.token_hex(16)
    try:
        from app.core.config import settings as app_settings
        tracking_url = f"{app_settings.TRACKING_PIXEL_URL}/pixel/{tracking_id}"
        result_msg = send_email(
            token_json=sending_token_json,
            sender=sender_email,
            to=contact.email,
            subject=email_content.get("subject", f"Application for {job.title}"),
            body=email_content.get("body", ""),
            tracking_pixel_url=tracking_url,
            pdf_path=cv_attach_path,
            sender_name=profile.name,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to send email: {e}")

    # 10. Record application
    pe_id = pe.id if pe and pe.gmail_token else None
    application = Application(
        job_id=job.id,
        profile_id=profile.id,
        profile_email_id=pe_id,
        to_email=contact.email,
        to_name=contact.name,
        subject=email_content.get("subject", ""),
        body=email_content.get("body", ""),
        cv_path=None,
        status=ApplicationStatus.sent,
        scheduled_at=_dt.utcnow(),
        sent_at=_dt.utcnow(),
        tracking_id=tracking_id,
        gmail_message_id=result_msg.get("id"),
        gmail_thread_id=result_msg.get("threadId"),
    )
    db.add(application)
    job.matched_profile_id = profile.id
    job.status = JobStatus.applied
    await db.commit()

    return {
        "message": f"Email sent to {contact.email} from {sender_email}",
        "profile": profile.name,
        "to": contact.email,
        "subject": email_content.get("subject"),
        "cv_attached": cv_attach_path is not None,
    }


@router.get("/activity-stats")
async def get_job_activity_stats(
    current_user=Depends(require_permission(Permission.manage_users)),
    db: AsyncSession = Depends(get_db),
):
    """Super admin: how many jobs were updated by each team member."""
    from sqlalchemy import func, text
    from app.models.job import JobActivity

    # Count contact_added + contact_updated activities grouped by user
    rows = await db.execute(
        select(
            JobActivity.user_id,
            JobActivity.user_name,
            JobActivity.user_role,
            func.count(JobActivity.id).label("total_updates"),
            func.count(func.distinct(JobActivity.job_id)).label("unique_jobs"),
        )
        .where(JobActivity.activity_type.in_([
            JobActivityType.contact_added,
            JobActivityType.contact_updated,
        ]))
        .group_by(JobActivity.user_id, JobActivity.user_name, JobActivity.user_role)
        .order_by(func.count(JobActivity.id).desc())
    )

    return [
        {
            "user_id": str(r.user_id) if r.user_id else None,
            "user_name": r.user_name,
            "user_role": r.user_role,
            "total_updates": r.total_updates,
            "unique_jobs_updated": r.unique_jobs,
        }
        for r in rows.all()
    ]


@router.post("/{job_id}/cv")
async def upload_job_cv(
    job_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user=Depends(require_permission(Permission.manage_jobs)),
    db: AsyncSession = Depends(get_db),
):
    """Upload a custom CV for a specific job — replaces the auto-selected one."""
    import os, shutil
    from app.core.config import settings

    if not file.filename.endswith((".pdf", ".docx", ".doc")):
        raise HTTPException(status_code=400, detail="Only PDF or Word documents are supported")

    app_r = await db.execute(select(Application).where(Application.job_id == job_id).order_by(Application.created_at.desc()))
    app = app_r.scalars().first()
    if not app:
        raise HTTPException(status_code=404, detail="No application found for this job")

    job_dir = os.path.join(settings.STORAGE_PATH, "job_cvs", str(job_id))
    os.makedirs(job_dir, exist_ok=True)
    file_path = os.path.join(job_dir, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    app.cv_path = file_path
    await db.commit()

    from app.core.config import settings as s
    storage_root = os.path.abspath(s.STORAGE_PATH)
    abs_path = os.path.abspath(file_path)
    cv_url = None
    if abs_path.startswith(storage_root):
        relative = abs_path[len(storage_root):].lstrip("/")
        cv_url = f"{s.APP_URL}/storage/{relative}"

    return {"message": "CV updated", "cv_url": cv_url}


@router.delete("/{job_id}/cv")
async def delete_job_cv(
    job_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_jobs)),
    db: AsyncSession = Depends(get_db),
):
    """Remove the CV attachment from a job's application."""
    app_r = await db.execute(select(Application).where(Application.job_id == job_id).order_by(Application.created_at.desc()))
    app = app_r.scalars().first()
    if not app:
        raise HTTPException(status_code=404, detail="No application found for this job")

    app.cv_path = None
    await db.commit()
    return {"message": "CV removed"}
