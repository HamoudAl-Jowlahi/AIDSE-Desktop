"""
AIDSE Platform — Projects Module ORM Models
Section 10.1 (ER Diagram: PROJECTS, PROJECT_MEMBERS, AUDIT_LOGS)
Section 10.2 (Key Constraints: UNIQUE(project_id, user_id) on project_members)
Section 13.3 (Audit Logs: append-only, no UPDATE/DELETE permitted at app layer)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.db.base import Base


class Project(Base):
    """
    Represents an AIDSE project — the top-level organizational unit.
    Maps to the PROJECTS entity in Section 10.1.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable project name",
    )
    project_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="general",
        comment="Project category (e.g. 'evaluation', 'automl', 'general')",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="FK to USERS — project creator and owner",
    )

    # Relationships
    members: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember", back_populates="project", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="project", cascade="all, delete-orphan"
    )
    datasets: Mapped[list["Dataset"]] = relationship(
        "Dataset", back_populates="project", cascade="all, delete-orphan"
    )
    golden_datasets: Mapped[list["GoldenDataset"]] = relationship(
        "GoldenDataset", back_populates="project", cascade="all, delete-orphan"
    )
    # These three reach Project through a plain backref or an uncascaded
    # relationship declared on the child. Without a cascade here SQLAlchemy
    # tries to NULL their project_id on delete, and all three columns are NOT
    # NULL — so deleting a project that had ever been used for training,
    # chatted about, or given a provider key failed with an IntegrityError.
    # passive_deletes=True matters as much as the cascade here. Every one of
    # these FKs is declared ondelete="CASCADE", so the database can clean up
    # on its own — but when the ORM has the collection loaded and no rule to
    # follow, it emits UPDATE ... SET project_id = NULL *before* the DELETE
    # and the NOT NULL constraint rejects it. passive_deletes tells the ORM to
    # step back and let the database do it, whether or not the collection
    # happens to be loaded.
    experiments: Mapped[list["Experiment"]] = relationship(
        "Experiment", back_populates="project",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="project",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    provider_credentials: Mapped[list["ProviderCredential"]] = relationship(
        "ProviderCredential", back_populates="project",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    # The evaluation_runs will be connected directly to golden_datasets per the SRS ERD
    # so we do not link them directly to Project unless we need a backref for convenience.

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r}>"


class ProjectMember(Base):
    """
    Project membership record — links a User to a Project with a role.
    Maps to PROJECT_MEMBERS entity in Section 10.1.
    UNIQUE(project_id, user_id) enforced in Section 10.2.
    """

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Role: viewer | editor | admin | owner (Section 13.2)",
    )
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="members")

    def __repr__(self) -> str:
        return f"<ProjectMember project={self.project_id} user={self.user_id} role={self.role}>"


class AuditLog(Base):
    """
    Immutable audit trail for all state-changing actions.
    Maps to AUDIT_LOGS entity in Section 10.1.
    Section 13.3: NO UPDATE or DELETE permitted at the application layer.
    Append-only: only INSERT is allowed from application code.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Project this audit log belongs to",
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="User who performed the action",
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Action performed (e.g. 'project_created', 'member_invited')",
    )
    target_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Resource type affected (e.g. 'project', 'member', 'evaluation_run')",
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        comment="UUID of the affected resource",
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        default=None,
        comment="Additional context (before/after values, relevant IDs, etc.)",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="When the action occurred — indexed for chronological retrieval",
    )

    # Relationship
    project: Mapped["Project"] = relationship("Project", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action} actor={self.actor_id} at={self.occurred_at}>"
