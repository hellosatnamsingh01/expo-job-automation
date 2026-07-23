from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base import get_db
from app.core.security import decode_token
from app.models.user import User, UserPermission, Permission, ROLE_DEFAULT_PERMISSIONS
import uuid

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_permission(permission: Permission):
    async def checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # Load per-user permission overrides
        result = await db.execute(
            select(UserPermission).where(UserPermission.user_id == current_user.id)
        )
        overrides = {p.permission: p.granted for p in result.scalars().all()}

        # Check override first, then role default
        if permission in overrides:
            has_perm = overrides[permission]
        else:
            has_perm = permission in ROLE_DEFAULT_PERMISSIONS.get(current_user.role, [])

        if not has_perm:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return current_user

    return checker


async def get_user_permissions(user: User, db: AsyncSession) -> set[Permission]:
    result = await db.execute(
        select(UserPermission).where(UserPermission.user_id == user.id)
    )
    overrides = {p.permission: p.granted for p in result.scalars().all()}
    base = set(ROLE_DEFAULT_PERMISSIONS.get(user.role, []))
    # Apply overrides
    for perm, granted in overrides.items():
        if granted:
            base.add(perm)
        else:
            base.discard(perm)
    return base
