"""
AIDSE Platform — Auth Module Pydantic Schemas
Section 11.2 (Auth API endpoints), Section 23.4 (Coding Standards)

All request/response schemas are typed via Pydantic v2.
No untyped dict passthroughs (Section 23.4).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """Request body for POST /auth/register (Section 11.2)."""

    name: str = Field(min_length=1, max_length=255, description="Display name")
    email: EmailStr = Field(description="User email — must be unique")
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Password (min 8 chars)",
    )

    @field_validator("password")
    @classmethod
    def password_must_have_complexity(cls, v: str) -> str:
        """Require at least one digit and one letter."""
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_letter and has_digit):
            raise ValueError("Password must contain at least one letter and one digit")
        return v


class LoginRequest(BaseModel):
    """Request body for POST /auth/login (Section 11.2)."""

    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    """Request body for POST /auth/refresh (Section 11.2)."""

    refresh_token: str | None = Field(default=None, min_length=1)


class TokenResponse(BaseModel):
    """Response for login and register (Section 11.2)."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


class AccessTokenResponse(BaseModel):
    """Response for token refresh — access token only."""

    access_token: str
    token_type: str = "Bearer"


class UserOut(BaseModel):
    """Safe user representation — no password_hash or internal fields."""

    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}
