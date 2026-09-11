"""
AIDSE Platform — Auth Module ORM Models
Section 10.1 (ER Diagram — USERS table), Section 13.1 (JWT token_version)
Section 13.4 (password stored as bcrypt hash, never plaintext)

Security note (Section 23.2 Rule 4):
- password_hash: bcrypt, cost ≥ 12. NEVER store plaintext passwords.
- token_version: integer, incremented on global logout to invalidate all tokens.
- refresh_token_hash: bcrypt hash of the last issued refresh token.
  Stored to support rotation detection (Section 13.1).
  NULL means no active refresh token (user has never logged in or has logged out).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base


class User(Base):
    """
    Represents a registered AIDSE user.
    Maps to the USERS entity in Section 10.1 ER diagram.
    """

    __tablename__ = "users"

    # Override id to ensure correct type annotation
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="User's email address — globally unique (Section 10.2)",
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="bcrypt hash, cost ≥ 12. Never plaintext (Section 13.4)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name",
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="user",
        comment="System-level role: 'user' or 'admin'",
    )
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment=(
            "Incremented on global logout to invalidate all issued tokens. "
            "Tokens carrying an older version are rejected (Section 13.1)."
        ),
    )
    refresh_token_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment=(
            "bcrypt hash of the current refresh token. "
            "Used for rotation + reuse detection (Section 13.1). "
            "NULL = no active refresh token."
        ),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Soft-disable a user account without deletion",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
