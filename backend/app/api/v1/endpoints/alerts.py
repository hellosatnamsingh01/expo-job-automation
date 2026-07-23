from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from app.db.base import get_db
from app.models.alert import SystemAlert
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/")
async def list_alerts(
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(SystemAlert).order_by(SystemAlert.created_at.desc()).limit(limit)
    )
    alerts = result.scalars().all()
    return [
        {
            "id": a.id,
            "type": a.type,
            "severity": a.severity,
            "title": a.title,
            "message": a.message,
            "source": a.source,
            "is_read": a.is_read,
            # Append Z so browsers parse as UTC, not local time
            "created_at": a.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    await db.execute(update(SystemAlert).values(is_read=True))
    await db.commit()
    return {"ok": True}


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(func.count()).select_from(SystemAlert).where(SystemAlert.is_read == False)
    )
    return {"count": result.scalar() or 0}


@router.delete("/{alert_id}")
async def dismiss_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    await db.execute(delete(SystemAlert).where(SystemAlert.id == alert_id))
    await db.commit()
    return {"ok": True}


@router.delete("/")
async def dismiss_all_alerts(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    await db.execute(delete(SystemAlert))
    await db.commit()
    return {"ok": True}
