"""
AIDSE Platform — Projects Module Pydantic Schemas
Section 11.2 (Projects API), Section 23.4 (Coding Standards)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Project Schemas ───────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    """Request body for POST /projects."""

    name: str = Field(min_length=1, max_length=255)
    project_type: str = Field(
        default="general",
        alias="type",
        description="Project category: 'evaluation', 'automl', 'general'",
    )
    description: str | None = Field(default=None, max_length=1000)

    model_config = {"populate_by_name": True}


class ProjectOut(BaseModel):
    """Public project representation."""

    id: uuid.UUID
    name: str
    project_type: str
    description: str | None
    owner_id: uuid.UUID
    created_at: datetime
    member_count: int = 0  # Populated by service layer

    model_config = {"from_attributes": True}


class ProjectListOut(BaseModel):
    """Paginated project list response."""

    items: list[ProjectOut]
    total: int
    page: int
    page_size: int


# ── Member Schemas ────────────────────────────────────────────────────────────

RoleType = Literal["viewer", "editor", "admin"]  # owner cannot be invited


class MemberInvite(BaseModel):
    """Request body for POST /projects/{id}/members."""

    email: str = Field(description="Email of the user to invite")
    role: RoleType = Field(description="Role to assign: viewer | editor | admin")


class MemberOut(BaseModel):
    """Public project member representation."""

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    invited_at: datetime
    # Denormalized from user (populated by service)
    user_name: str | None = None
    user_email: str | None = None

    model_config = {"from_attributes": True}


# ── Audit Log Schemas ─────────────────────────────────────────────────────────

class AuditLogOut(BaseModel):
    """Public audit log entry (Section 13.3)."""

    id: uuid.UUID
    project_id: uuid.UUID
    actor_id: uuid.UUID
    action: str
    target_type: str
    target_id: uuid.UUID | None
    metadata_: dict | None = Field(None, alias="metadata")
    occurred_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
