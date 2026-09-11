"""
AIDSE Platform — FastAPI Shared Dependencies
Section 13.2 (RBAC), Section 23.4 (Coding Standards)

Security note (Section 23.2 Rule 4):
RBAC is enforced HERE at the API layer via FastAPI dependencies,
not at the UI layer. Every protected endpoint must declare the
appropriate dependency — there is no implicit authorization.

token_version check:
  The JWT carries the token_version at issuance time.
  On each request, we re-read the user's current token_version from DB.
  If they differ, the token was issued before a global logout —
  reject with 401 even if the JWT signature is valid.
"""
from __future__ import annotations

import uuid
from enum import IntEnum

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.security import decode_token
from apps.api.db.session import get_db
from apps.api.modules.auth.models import User
from apps.api.modules.auth.schemas import UserOut

DEFAULT_DESKTOP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_bearer = HTTPBearer(auto_error=False)


class ProjectRole(IntEnum):
    """RBAC role hierarchy for project membership (Section 13.2).

    Higher integer = more permissions.
    Used by require_project_role() to enforce minimum role.
    """

    VIEWER = 10
    EDITOR = 20
    ADMIN = 30
    OWNER = 40


ROLE_ORDER: dict[str, ProjectRole] = {
    "viewer": ProjectRole.VIEWER,
    "editor": ProjectRole.EDITOR,
    "admin": ProjectRole.ADMIN,
    "owner": ProjectRole.OWNER,
}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """
    FastAPI dependency: validate Bearer JWT and return the current user.

    In desktop mode (or SQLite local execution without token), automatically
    provides the local desktop admin user context.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or expired token"}},
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        import os
        if os.getenv("AIDSE_DESKTOP_MODE") == "1":
            user = await db.scalar(select(User).where((User.id == DEFAULT_DESKTOP_USER_ID) | (User.email == "local@aidse.internal")))
            if user is not None and user.is_active:
                return UserOut.model_validate(user)
            import datetime
            return UserOut(
                id=DEFAULT_DESKTOP_USER_ID,
                email="local@aidse.internal",
                name="AIDSE Analyst",
                role="admin",
                is_active=True,
                created_at=datetime.datetime.now(datetime.timezone.utc),
                last_login_at=None,
            )
        raise credentials_exception

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise credentials_exception

    if payload.get("type") != "access":
        raise credentials_exception

    user_id_str: str | None = payload.get("sub")
    token_version: int | None = payload.get("token_version")

    if not user_id_str or token_version is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    user = await db.get(User, user_id)

    if user is None or not user.is_active:
        raise credentials_exception

    # token_version check — global logout detection
    if user.token_version != token_version:
        raise credentials_exception

    return UserOut.model_validate(user)


def require_project_role(min_role: ProjectRole):  # noqa: ANN201
    """
    FastAPI dependency factory: require the current user to have at least
    `min_role` in the requested project.
    """
    from apps.api.modules.projects.models import Project, ProjectMember

    async def _check(
        project_id: uuid.UUID,
        current_user: UserOut = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        member = await db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == current_user.id,
            )
        )
        if member is None:
            # Check if project exists
            proj = await db.scalar(select(Project).where(Project.id == project_id))
            if proj is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": {"code": "NOT_FOUND", "message": "Project not found"}},
                )
            if current_user.id == DEFAULT_DESKTOP_USER_ID or current_user.role == "admin":
                # In desktop admin mode, grant full access to existing local projects
                return
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "NOT_FOUND", "message": "Project not found"}},
            )
        member_role_value = ROLE_ORDER.get(member.role, ProjectRole.VIEWER)
        if member_role_value < min_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": f"Requires {min_role.name} role or higher",
                    }
                },
            )

    return _check
