"""
AIDSE Platform — Projects Module Router
Section 11.2 (Projects API endpoints), Section 13.2 (RBAC)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.dependencies import ProjectRole, get_current_user, require_project_role
from apps.api.db.session import get_db
from apps.api.modules.auth.schemas import UserOut
from apps.api.modules.projects import service
from apps.api.modules.projects.schemas import (
    AuditLogOut,
    MemberInvite,
    MemberOut,
    ProjectCreate,
    ProjectListOut,
    ProjectOut,
)
from apps.api.modules.projects.service import (
    MemberAlreadyExistsError,
    ProjectError,
    ProjectNotFoundError,
    UserNotFoundError,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


def _project_error_to_http(exc: ProjectError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": {"code": "PROJECT_ERROR", "message": str(exc)}},
    )


@router.get(
    "",
    response_model=ProjectListOut,
    status_code=status.HTTP_200_OK,
    summary="List user's projects",
)
async def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectListOut:
    """GET /api/v1/projects — Section 11.2"""
    return await service.list_projects(db, current_user, page, page_size)


@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    payload: ProjectCreate,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    """POST /api/v1/projects — Section 11.2"""
    return await service.create_project(db, payload, current_user)


@router.get(
    "/{project_id}",
    response_model=ProjectOut,
    status_code=status.HTTP_200_OK,
    summary="Get project details",
)
async def get_project(
    project_id: uuid.UUID,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    """GET /api/v1/projects/{id} — Section 11.2"""
    try:
        return await service.get_project(db, project_id, current_user)
    except ProjectNotFoundError as exc:
        raise _project_error_to_http(exc) from exc


@router.post(
    "/{project_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user to this project",
    dependencies=[Depends(require_project_role(ProjectRole.ADMIN))],
)
async def invite_member(
    project_id: uuid.UUID,
    payload: MemberInvite,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberOut:
    """POST /api/v1/projects/{id}/members — Section 11.2 (requires admin/owner)"""
    try:
        return await service.invite_member(db, project_id, payload, current_user)
    except (MemberAlreadyExistsError, UserNotFoundError, ProjectNotFoundError) as exc:
        raise _project_error_to_http(exc) from exc


@router.get(
    "/{project_id}/audit-logs",
    response_model=list[AuditLogOut],
    status_code=status.HTTP_200_OK,
    summary="Get project audit log",
    dependencies=[Depends(require_project_role(ProjectRole.ADMIN))],
)
async def list_audit_logs(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogOut]:
    """GET /api/v1/projects/{id}/audit-logs — Section 11.2 (requires admin/owner)"""
    try:
        return await service.list_audit_logs(db, project_id, current_user, page, page_size)
    except ProjectNotFoundError as exc:
        raise _project_error_to_http(exc) from exc


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
    dependencies=[Depends(require_project_role(ProjectRole.OWNER))],
)
async def delete_project(
    project_id: uuid.UUID,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DELETE /api/v1/projects/{id} — Requires owner role"""
    try:
        await service.delete_project(db, project_id, current_user)
    except ProjectNotFoundError as exc:
        raise _project_error_to_http(exc) from exc
