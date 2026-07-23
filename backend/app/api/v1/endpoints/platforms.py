from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import uuid

from app.db.base import get_db
from app.models.platform import Platform, ScrapeType
from app.models.job import Job
from app.models.user import Permission
from app.core.deps import require_permission, get_current_user

router = APIRouter()


class PlatformCreate(BaseModel):
    name: str
    url: str
    scrape_type: ScrapeType = ScrapeType.custom
    scrape_config: Optional[dict] = None
    keywords: Optional[str] = None
    scrape_frequency_hours: int = 24


class PlatformUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    keywords: Optional[str] = None
    scrape_frequency_hours: Optional[int] = None
    is_active: Optional[bool] = None
    scrape_config: Optional[dict] = None


@router.get("/")
async def list_platforms(
    current_user=Depends(require_permission(Permission.view_platforms)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Platform))
    platforms = result.scalars().all()
    out = []
    for p in platforms:
        count_r = await db.execute(select(func.count()).where(Job.platform_id == p.id))
        job_count = count_r.scalar() or 0
        # manually uploaded jobs associated by any means count separately
        out.append({
            "id": str(p.id),
            "name": p.name,
            "url": p.url,
            "scrape_type": p.scrape_type,
            "keywords": p.keywords,
            "scrape_frequency_hours": p.scrape_frequency_hours,
            "is_active": p.is_active,
            "last_scraped_at": p.last_scraped_at,
            "total_jobs_synced": job_count,
            "scrape_config": p.scrape_config,
        })
    return out


@router.post("/")
async def create_platform(
    data: PlatformCreate,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    platform = Platform(
        name=data.name,
        url=data.url,
        scrape_type=data.scrape_type,
        scrape_config=data.scrape_config,
        keywords=data.keywords,
        scrape_frequency_hours=data.scrape_frequency_hours,
        added_by_id=current_user.id,
    )
    db.add(platform)
    await db.commit()
    return {"id": str(platform.id), "message": "Platform added"}


@router.patch("/{platform_id}")
async def update_platform(
    platform_id: uuid.UUID,
    data: PlatformUpdate,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Platform).where(Platform.id == platform_id))
    platform = result.scalar_one_or_none()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(platform, field, value)
    await db.commit()
    return {"message": "Updated"}


@router.post("/scrape-all")
async def trigger_scrape_all(
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    from app.tasks.scraper import scrape_platform_task
    result = await db.execute(select(Platform).where(Platform.is_active == True))
    platforms = result.scalars().all()
    for p in platforms:
        scrape_platform_task.delay(str(p.id))
    return {"message": f"Queued {len(platforms)} platform(s)"}


@router.post("/enrich-descriptions")
async def trigger_enrich_descriptions(
    current_user=Depends(require_permission(Permission.manage_platforms)),
):
    from app.tasks.scraper import enrich_job_descriptions_task
    enrich_job_descriptions_task.delay()
    return {"message": "Job description enrichment queued"}


@router.post("/{platform_id}/scrape")
async def trigger_scrape(
    platform_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    from app.tasks.scraper import scrape_platform_task
    scrape_platform_task.delay(str(platform_id))
    return {"message": "Scrape job queued"}


@router.delete("/{platform_id}")
async def delete_platform(
    platform_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Platform).where(Platform.id == platform_id))
    platform = result.scalar_one_or_none()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")
    await db.delete(platform)
    await db.commit()
    return {"message": "Deleted"}
