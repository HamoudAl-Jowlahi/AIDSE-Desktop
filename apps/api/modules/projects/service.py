"""
AIDSE Platform — Projects Module Service
Section 18.2 (Phase 0 — Project & Membership Model), Section 13.3 (Audit Logs)
Section 23.4 (Coding Standards): all business logic in service.py

Responsibility: Implements project CRUD, member invitation, and audit logging.
Audit logs are append-only; this module NEVER calls UPDATE or DELETE on audit_logs.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.modules.auth.models import User
from apps.api.modules.auth.schemas import UserOut
from apps.api.modules.projects.models import AuditLog, Project, ProjectMember
from apps.api.modules.projects.schemas import (
    AuditLogOut,
    MemberInvite,
    MemberOut,
    ProjectCreate,
    ProjectListOut,
    ProjectOut,
)


class ProjectError(Exception):
    """Domain error for project operations."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProjectNotFoundError(ProjectError):
    def __init__(self) -> None:
        super().__init__("Project not found", status_code=404)


class MemberAlreadyExistsError(ProjectError):
    def __init__(self) -> None:
        super().__init__("User is already a member of this project", status_code=409)


class UserNotFoundError(ProjectError):
    def __init__(self) -> None:
        super().__init__("No user found with that email address", status_code=404)


async def _write_audit_log(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Append an immutable audit log entry (Section 13.3).
    NEVER call update or delete on this table from application code.
    """
    log = AuditLog(
        project_id=project_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_=metadata,
    )
    db.add(log)
    await db.flush()


async def create_project(
    db: AsyncSession,
    payload: ProjectCreate,
    current_user: UserOut,
) -> ProjectOut:
    """
    Create a new project.

    - Creates the Project record
    - Auto-adds creator as 'owner' member (Section 18.2)
    - Writes project_created audit log entry
    """
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name=payload.name,
        project_type=payload.project_type,
        description=payload.description,
        owner_id=current_user.id,
    )
    owner_member = ProjectMember(
        project_id=project_id,
        user_id=current_user.id,
        role="owner",
    )
    log = AuditLog(
        project_id=project_id,
        actor_id=current_user.id,
        action="project_created",
        target_type="project",
        target_id=project_id,
        metadata_={"name": project.name, "project_type": project.project_type},
    )
    db.add(project)
    db.add(owner_member)
    db.add(log)
    await db.flush()

    return ProjectOut(
        id=project.id,
        name=project.name,
        project_type=project.project_type,
        description=project.description,
        owner_id=project.owner_id,
        created_at=project.created_at,
        member_count=1,
    )


async def list_projects(
    db: AsyncSession,
    current_user: UserOut,
    page: int = 1,
    page_size: int = 20,
) -> ProjectListOut:
    """List all projects the current user is a member of."""
    offset = (page - 1) * page_size

    from apps.api.core.dependencies import DEFAULT_DESKTOP_USER_ID
    if current_user.id == DEFAULT_DESKTOP_USER_ID or current_user.role == "admin":
        total_stmt = select(func.count()).select_from(Project)
        total: int = await db.scalar(total_stmt) or 0
        projects_stmt = (
            select(Project)
            .order_by(Project.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    else:
        # Get project IDs the user is a member of
        member_subq = select(ProjectMember.project_id).where(
            ProjectMember.user_id == current_user.id
        )

        total_stmt = select(func.count()).select_from(Project).where(
            Project.id.in_(member_subq)
        )
        total: int = await db.scalar(total_stmt) or 0

        projects_stmt = (
            select(Project)
            .where(Project.id.in_(member_subq))
            .order_by(Project.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    result = await db.execute(projects_stmt)
    projects = result.scalars().all()

    # Get member counts
    items = []
    for p in projects:
        count_stmt = select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == p.id
        )
        member_count: int = await db.scalar(count_stmt) or 0
        items.append(
            ProjectOut(
                id=p.id,
                name=p.name,
                project_type=p.project_type,
                description=p.description,
                owner_id=p.owner_id,
                created_at=p.created_at,
                member_count=member_count,
            )
        )

    return ProjectListOut(items=items, total=total, page=page, page_size=page_size)


async def get_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    current_user: UserOut,
) -> ProjectOut:
    """
    Get a project by ID.
    Returns 404 if project doesn't exist OR user is not a member
    (to avoid leaking project existence to non-members).
    """
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    if member is None:
        from apps.api.core.dependencies import DEFAULT_DESKTOP_USER_ID
        if current_user.id == DEFAULT_DESKTOP_USER_ID or current_user.role == "admin":
            project = await db.get(Project, project_id)
            if project is not None:
                count_stmt = select(func.count()).select_from(ProjectMember).where(
                    ProjectMember.project_id == project.id
                )
                member_count: int = await db.scalar(count_stmt) or 1
                return ProjectOut(
                    id=project.id,
                    name=project.name,
                    project_type=project.project_type,
                    description=project.description,
                    owner_id=project.owner_id,
                    created_at=project.created_at,
                    member_count=member_count,
                )
        raise ProjectNotFoundError()

    project = await db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()

    count_stmt = select(func.count()).select_from(ProjectMember).where(
        ProjectMember.project_id == project.id
    )
    member_count: int = await db.scalar(count_stmt) or 0

    return ProjectOut(
        id=project.id,
        name=project.name,
        project_type=project.project_type,
        description=project.description,
        owner_id=project.owner_id,
        created_at=project.created_at,
        member_count=member_count,
    )


async def invite_member(
    db: AsyncSession,
    project_id: uuid.UUID,
    payload: MemberInvite,
    current_user: UserOut,
) -> MemberOut:
    """
    Invite a user to a project by email.

    - Looks up the invitee by email
    - Creates ProjectMember record
    - Writes member_invited audit log entry
    - Raises 409 if user is already a member (UNIQUE constraint)
    """
    # Verify project exists and actor is a member (already checked by RBAC dep)
    project = await db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()

    # Look up invitee by email
    invitee = await db.scalar(select(User).where(User.email == payload.email))
    if invitee is None:
        raise UserNotFoundError()

    # Create member record
    try:
        member = ProjectMember(
            project_id=project_id,
            user_id=invitee.id,
            role=payload.role,
        )
        db.add(member)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise MemberAlreadyExistsError()

    # Audit log
    await _write_audit_log(
        db,
        project_id=project_id,
        actor_id=current_user.id,
        action="member_invited",
        target_type="member",
        target_id=member.id,
        metadata={
            "invitee_email": invitee.email,
            "role": payload.role,
        },
    )

    return MemberOut(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        invited_at=member.invited_at,
        user_name=invitee.name,
        user_email=invitee.email,
    )


async def list_audit_logs(
    db: AsyncSession,
    project_id: uuid.UUID,
    current_user: UserOut,
    page: int = 1,
    page_size: int = 50,
) -> list[AuditLogOut]:
    """
    Return paginated audit logs for a project in reverse chronological order.
    Caller must verify admin/owner role via RBAC dependency.
    """
    offset = (page - 1) * page_size
    stmt = (
        select(AuditLog)
        .where(AuditLog.project_id == project_id)
        .order_by(AuditLog.occurred_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        AuditLogOut(
            id=log.id,
            project_id=log.project_id,
            actor_id=log.actor_id,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            metadata=log.metadata_,
            occurred_at=log.occurred_at,
        )
        for log in logs
    ]


async def delete_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    current_user: UserOut,
) -> None:
    """
    Delete a project and all associated cascading resources.
    """
    stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise ProjectNotFoundError()
    await db.delete(project)
    await db.commit()
