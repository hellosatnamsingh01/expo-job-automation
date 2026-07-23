from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid

from app.db.base import get_db
from app.models.user import User, UserPermission, UserRole, Permission, ROLE_DEFAULT_PERMISSIONS
from app.core.deps import get_current_user, require_permission
from app.core.security import get_password_hash

router = APIRouter()


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.researcher


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class PermissionUpdate(BaseModel):
    permissions: dict[str, bool]  # permission_key -> granted (True) or revoked (False)


@router.post("/")
async def create_user(
    data: UserCreate,
    current_user: User = Depends(require_permission(Permission.manage_users)),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=get_password_hash(data.password),
        role=data.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return {"id": str(user.id), "message": "Team member created"}


@router.get("/")
async def list_users(
    current_user: User = Depends(require_permission(Permission.manage_users)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    current_user: User = Depends(require_permission(Permission.manage_users)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    await db.commit()
    return {"message": "Updated"}


@router.put("/{user_id}/permissions")
async def set_user_permissions(
    user_id: uuid.UUID,
    data: PermissionUpdate,
    current_user: User = Depends(require_permission(Permission.manage_roles)),
    db: AsyncSession = Depends(get_db),
):
    # Delete existing overrides
    await db.execute(delete(UserPermission).where(UserPermission.user_id == user_id))

    # Insert new overrides
    for perm_key, granted in data.permissions.items():
        try:
            perm = Permission(perm_key)
        except ValueError:
            continue
        db.add(UserPermission(user_id=user_id, permission=perm, granted=granted))

    await db.commit()
    return {"message": "Permissions updated"}


@router.get("/{user_id}/permissions")
async def get_user_permissions_endpoint(
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.manage_roles)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    overrides_result = await db.execute(
        select(UserPermission).where(UserPermission.user_id == user_id)
    )
    overrides = {p.permission: p.granted for p in overrides_result.scalars().all()}
    role_defaults = set(ROLE_DEFAULT_PERMISSIONS.get(user.role, []))

    all_permissions = {}
    for perm in Permission:
        if perm in overrides:
            all_permissions[perm.value] = {"has": overrides[perm], "source": "override"}
        else:
            all_permissions[perm.value] = {"has": perm in role_defaults, "source": "role"}

    return {"role": user.role, "permissions": all_permissions}


@router.delete("/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.manage_users)),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return {"message": "Deleted"}
