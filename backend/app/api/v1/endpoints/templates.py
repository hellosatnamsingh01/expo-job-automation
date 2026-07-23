from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid

from app.db.base import get_db
from app.models.email_template import EmailTemplate, TemplateType
from app.models.user import Permission
from app.core.deps import require_permission

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    template_type: TemplateType
    subject: str
    body: str
    is_default: bool = False
    industry: Optional[str] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    industry: Optional[str] = None


@router.get("/")
async def list_templates(
    template_type: Optional[TemplateType] = None,
    current_user=Depends(require_permission(Permission.manage_templates)),
    db: AsyncSession = Depends(get_db),
):
    query = select(EmailTemplate)
    if template_type:
        query = query.where(EmailTemplate.template_type == template_type)
    result = await db.execute(query)
    templates = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "template_type": t.template_type,
            "industry": t.industry,
            "subject": t.subject,
            "body": t.body,
            "is_active": t.is_active,
            "is_default": t.is_default,
            "times_used": t.times_used,
            "open_count": t.open_count,
            "reply_count": t.reply_count,
        }
        for t in templates
    ]


@router.post("/")
async def create_template(
    data: TemplateCreate,
    current_user=Depends(require_permission(Permission.manage_templates)),
    db: AsyncSession = Depends(get_db),
):
    if data.is_default:
        # Unset existing default for this type + industry combination
        q = select(EmailTemplate).where(
            EmailTemplate.template_type == data.template_type,
            EmailTemplate.is_default == True,
            EmailTemplate.industry == data.industry,
        )
        existing = await db.execute(q)
        for t in existing.scalars().all():
            t.is_default = False

    template = EmailTemplate(**data.model_dump())
    db.add(template)
    await db.commit()
    return {"id": str(template.id), "message": "Template created"}


@router.patch("/{template_id}")
async def update_template(
    template_id: uuid.UUID,
    data: TemplateUpdate,
    current_user=Depends(require_permission(Permission.manage_templates)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(template, field, value)
    await db.commit()
    return {"message": "Updated"}


@router.delete("/{template_id}")
async def delete_template(
    template_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_templates)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(template)
    await db.commit()
    return {"message": "Deleted"}
