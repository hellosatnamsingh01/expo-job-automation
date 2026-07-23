from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
import uuid, os, shutil

from app.db.base import get_db
from app.models.profile import Profile, ProfileSkill, ProfileCV, ProfileEmail, SkillType
from app.models.user import Permission
from app.core.deps import get_current_user, require_permission
from app.core.config import settings

router = APIRouter()


class SkillIn(BaseModel):
    skill: str
    skill_type: SkillType


class ProfileCreate(BaseModel):
    name: str
    email: Optional[str] = None
    bio: Optional[str] = None
    years_experience: Optional[int] = None
    skills: List[SkillIn] = []


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None
    years_experience: Optional[int] = None
    is_active: Optional[bool] = None
    skills: Optional[List[SkillIn]] = None


@router.get("/")
async def list_profiles(
    current_user=Depends(require_permission(Permission.view_profiles)),
    db: AsyncSession = Depends(get_db),
):
    from app.models.application import Application, ApplicationStatus
    from app.models.job import Job
    from sqlalchemy import func

    result = await db.execute(select(Profile))
    profiles = result.scalars().all()
    out = []
    for p in profiles:
        skills_r = await db.execute(select(ProfileSkill).where(ProfileSkill.profile_id == p.id))
        cvs_r = await db.execute(select(ProfileCV).where(ProfileCV.profile_id == p.id, ProfileCV.is_active == True).order_by(ProfileCV.uploaded_at.desc()))
        emails_r = await db.execute(select(ProfileEmail).where(ProfileEmail.profile_id == p.id))
        profile_emails = emails_r.scalars().all()

        # Profile-level job counts
        total_jobs = await db.execute(
            select(func.count(Job.id)).where(Job.matched_profile_id == p.id)
        )
        sent_jobs = await db.execute(
            select(func.count(Application.id)).where(
                Application.profile_id == p.id,
                Application.sent_at.isnot(None),
            )
        )
        queued_jobs = await db.execute(
            select(func.count(Application.id)).where(
                Application.profile_id == p.id,
                Application.status == ApplicationStatus.scheduled,
                Application.sent_at.is_(None),
            )
        )

        # Jobs matched but no application created yet (still researching)
        from sqlalchemy import not_, exists
        unassigned_jobs = await db.execute(
            select(func.count(Job.id)).where(
                Job.matched_profile_id == p.id,
                ~exists().where(Application.job_id == Job.id),
            )
        )
        unassigned_count = unassigned_jobs.scalar() or 0

        # Per-email stats
        email_list = []
        for e in profile_emails:
            sent = await db.execute(
                select(func.count(Application.id)).where(
                    Application.sender_email == e.email,
                    Application.sent_at.isnot(None),
                )
            )
            scheduled = await db.execute(
                select(func.count(Application.id)).where(
                    Application.sender_email == e.email,
                    Application.status == ApplicationStatus.scheduled,
                    Application.sent_at.is_(None),
                )
            )
            app_assigned = await db.execute(
                select(func.count(Application.id)).where(
                    Application.sender_email == e.email,
                )
            )
            app_count = app_assigned.scalar() or 0
            # Primary email gets credited with all unassigned (researching) jobs
            total_assigned = app_count + (unassigned_count if e.is_primary else 0)

            email_list.append({
                "id": str(e.id),
                "email": e.email,
                "is_primary": e.is_primary,
                "assigned_count": total_assigned,
                "sent_count": sent.scalar() or 0,
                "scheduled_count": scheduled.scalar() or 0,
            })

        out.append({
            "id": str(p.id),
            "name": p.name,
            "email": p.email,
            "bio": p.bio,
            "years_experience": p.years_experience,
            "is_active": p.is_active,
            "total_jobs": total_jobs.scalar() or 0,
            "sent_jobs": sent_jobs.scalar() or 0,
            "queued_jobs": queued_jobs.scalar() or 0,
            "skills": [{"skill": s.skill, "type": s.skill_type} for s in skills_r.scalars().all()],
            "cvs": [{"id": str(c.id), "file_name": c.file_name, "region": c.region, "is_active": c.is_active, "uploaded_at": c.uploaded_at} for c in cvs_r.scalars().all()],
            "emails": email_list,
        })
    return out


@router.post("/")
async def create_profile(
    data: ProfileCreate,
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    profile = Profile(name=data.name, email=data.email, bio=data.bio, years_experience=data.years_experience)
    db.add(profile)
    await db.flush()
    for s in data.skills:
        db.add(ProfileSkill(profile_id=profile.id, skill=s.skill, skill_type=s.skill_type))
    await db.commit()
    # Trigger matching so existing skipped/new jobs get evaluated against this new profile
    from app.tasks.matcher import match_all_unmatched_task
    match_all_unmatched_task.delay()
    return {"id": str(profile.id), "message": "Profile created"}


@router.patch("/{profile_id}")
async def update_profile(
    profile_id: uuid.UUID,
    data: ProfileUpdate,
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    dump = data.model_dump(exclude_none=True)
    skills = dump.pop("skills", None)

    for field, value in dump.items():
        setattr(profile, field, value)

    if skills is not None:
        await db.execute(
            __import__("sqlalchemy", fromlist=["delete"]).delete(ProfileSkill).where(ProfileSkill.profile_id == profile_id)
        )
        for s in skills:
            db.add(ProfileSkill(profile_id=profile_id, skill=s["skill"], skill_type=s["skill_type"]))

    await db.commit()
    # Re-run matching in case skills changed — picks up skipped jobs that now match
    from app.tasks.matcher import match_all_unmatched_task
    match_all_unmatched_task.delay()
    return {"message": "Updated"}


@router.post("/{profile_id}/skills")
async def add_skill(
    profile_id: uuid.UUID,
    data: SkillIn,
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    db.add(ProfileSkill(profile_id=profile_id, skill=data.skill, skill_type=data.skill_type))
    await db.commit()
    return {"message": "Skill added"}


@router.delete("/{profile_id}/skills/{skill_id}")
async def delete_skill(
    profile_id: uuid.UUID,
    skill_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProfileSkill).where(ProfileSkill.id == skill_id, ProfileSkill.profile_id == profile_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/{profile_id}/cv")
async def upload_cv(
    profile_id: uuid.UUID,
    file: UploadFile = File(...),
    region: str | None = Form(None),
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.endswith((".docx", ".doc", ".pdf")):
        raise HTTPException(status_code=400, detail="Only Word documents (.docx/.doc) or PDF files are supported")

    valid_regions = {
        None, "OTHER",
        "US", "CA", "UK", "AU", "AE", "IN", "DE",
        "NZ", "SG", "PK", "IE", "ZA", "NG", "KE",
        "FR", "NL", "SE", "DK", "NO", "FI", "IT", "ES",
    }
    if region not in valid_regions:
        raise HTTPException(status_code=400, detail=f"Invalid region '{region}'")

    profile_dir = os.path.join(settings.STORAGE_PATH, "cvs", str(profile_id))
    os.makedirs(profile_dir, exist_ok=True)
    file_path = os.path.join(profile_dir, file.filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # If uploading a region-specific CV, deactivate any existing CV for that same region
    # If no region (default), deactivate existing default CVs only
    prev = await db.execute(
        select(ProfileCV).where(
            ProfileCV.profile_id == profile_id,
            ProfileCV.region == region,
            ProfileCV.is_active == True,
        )
    )
    for cv in prev.scalars().all():
        cv.is_active = False

    cv = ProfileCV(profile_id=profile_id, file_name=file.filename, file_path=file_path, is_active=True, region=region)
    db.add(cv)
    await db.commit()
    return {"id": str(cv.id), "file_name": file.filename, "region": region, "message": "CV uploaded"}


@router.get("/{profile_id}/cv/{cv_id}/download")
async def download_cv(
    profile_id: uuid.UUID,
    cv_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.view_profiles)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProfileCV).where(ProfileCV.id == cv_id, ProfileCV.profile_id == profile_id))
    cv = result.scalar_one_or_none()
    if not cv:
        raise HTTPException(status_code=404, detail="CV not found")
    if not cv.file_path or not os.path.exists(cv.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(cv.file_path, filename=cv.file_name, media_type="application/octet-stream")


@router.delete("/{profile_id}/cv/{cv_id}")
async def delete_cv(
    profile_id: uuid.UUID,
    cv_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProfileCV).where(ProfileCV.id == cv_id, ProfileCV.profile_id == profile_id))
    cv = result.scalar_one_or_none()
    if not cv:
        raise HTTPException(status_code=404, detail="CV not found")
    try:
        if cv.file_path and os.path.exists(cv.file_path):
            os.remove(cv.file_path)
    except Exception:
        pass
    await db.delete(cv)
    await db.commit()
    return {"message": "CV deleted"}


class ProfileEmailIn(BaseModel):
    email: str
    is_primary: bool = False

@router.post("/{profile_id}/emails")
async def add_email(
    profile_id: uuid.UUID,
    data: ProfileEmailIn,
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    email = data.email
    is_primary = data.is_primary
    # Idempotent: if this email is already linked, just update is_primary
    existing = await db.execute(
        select(ProfileEmail).where(ProfileEmail.profile_id == profile_id, ProfileEmail.email == email)
    )
    pe = existing.scalar_one_or_none()
    if pe:
        if is_primary:
            prev = await db.execute(select(ProfileEmail).where(ProfileEmail.profile_id == profile_id, ProfileEmail.is_primary == True))
            for e in prev.scalars().all():
                e.is_primary = False
            pe.is_primary = True
        await db.commit()
        return {"message": "Email already linked"}

    if is_primary:
        prev = await db.execute(select(ProfileEmail).where(ProfileEmail.profile_id == profile_id, ProfileEmail.is_primary == True))
        for e in prev.scalars().all():
            e.is_primary = False
    db.add(ProfileEmail(profile_id=profile_id, email=email, is_primary=is_primary))
    await db.commit()
    return {"message": "Email added"}


@router.delete("/{profile_id}/emails/{email_id}")
async def delete_profile_email(
    profile_id: uuid.UUID,
    email_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfileEmail).where(ProfileEmail.id == email_id, ProfileEmail.profile_id == profile_id)
    )
    pe = result.scalar_one_or_none()
    if not pe:
        raise HTTPException(status_code=404, detail="Email not found")

    # If deleting primary, promote the next available email to primary
    if pe.is_primary:
        others = await db.execute(
            select(ProfileEmail).where(
                ProfileEmail.profile_id == profile_id,
                ProfileEmail.id != email_id,
            )
        )
        next_pe = others.scalars().first()
        if next_pe:
            next_pe.is_primary = True
        # If no others, allow deletion anyway (profile will have no emails)

    await db.delete(pe)
    await db.commit()
    return {"message": "Email removed"}


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_profiles)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    pid_str = str(profile_id)
    # Delete dependent rows that have NOT NULL FK constraints
    await db.execute(text(f"DELETE FROM application_followups WHERE application_id IN (SELECT id FROM applications WHERE profile_id = '{pid_str}'::uuid)"))
    await db.execute(text(f"DELETE FROM applications WHERE profile_id = '{pid_str}'::uuid"))
    await db.execute(text(f"UPDATE jobs SET matched_profile_id = NULL WHERE matched_profile_id = '{pid_str}'::uuid"))
    await db.flush()
    await db.delete(profile)
    await db.commit()
    return {"message": "Deleted"}
