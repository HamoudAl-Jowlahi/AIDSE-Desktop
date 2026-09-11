"""
AIDSE Platform — SQLAlchemy ORM Base
Section 10 (Database Design), Section 12.1 (Folder Structure)

All ORM models inherit from Base declared here.
UUID primary keys used throughout (Section 10.1).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all AIDSE ORM models.

    Provides:
    - UUID primary key (id)
    - created_at timestamp with automatic DB-level default
    """

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-10,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        sort_order=-9,
    )
