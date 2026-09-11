"""
AIDSE Platform — Auth Module Service
Section 18.2 (Phase 0 — Authentication System), Section 13.1 (JWT)
Section 23.4 (Coding Standards): all business logic in service.py

Responsibility: Implements all authentication business logic including
user registration, login, token issuance, refresh rotation, and global logout.
No request/response handling here — only DB + token operations.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)


def _digest_token(token: str) -> str:
    """Kept for documentation only — prehashing now done inside hash_password/verify_password."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()
from apps.api.modules.auth.models import User
from apps.api.modules.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)


class AuthError(Exception):
    """Domain error for authentication failures."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class DuplicateEmailError(AuthError):
    """Raised when registering with an already-used email."""

    def __init__(self) -> None:
        super().__init__("Email already registered", status_code=409)


async def register_user(
    db: AsyncSession, payload: RegisterRequest
) -> TokenResponse:
    """
    Register a new user and issue initial tokens.

    Steps:
    1. Check email uniqueness (raises DuplicateEmailError on collision)
    2. Hash password with bcrypt
    3. Create User record
    4. Issue access + refresh tokens (token_version=0)
    5. Store hashed refresh token in DB
    """
    # 1. Check uniqueness
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise DuplicateEmailError()

    # 2. Hash password
    password_hash = hash_password(payload.password)

    # 3. Create user
    user = User(
        email=payload.email,
        name=payload.name,
        password_hash=password_hash,
        role="user",
        token_version=0,
    )
    db.add(user)
    await db.flush()  # Get the UUID assigned

    # 4. Issue tokens
    access_token = create_access_token(user.id, user.role, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)

    # 5. Store hashed refresh token
    user.refresh_token_hash = hash_password(refresh_token)
    await db.flush()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def authenticate_user(
    db: AsyncSession, payload: LoginRequest
) -> TokenResponse:
    """
    Authenticate a user by email+password and issue tokens.

    Returns 401 for unknown email OR wrong password (no user enumeration).
    Updates last_login_at on success.
    """
    user = await db.scalar(select(User).where(User.email == payload.email))

    # Constant-time check: always verify even if user is None (prevent timing attacks)
    # The dummy hash is a valid bcrypt hash of a known string, used only for timing
    _DUMMY_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj2NJbOjqZhO"  # noqa: S105
    password_valid = (
        verify_password(payload.password, user.password_hash)
        if user is not None
        else verify_password("dummy", _DUMMY_HASH)
    )

    if user is None or not password_valid or not user.is_active:
        raise AuthError("Invalid email or password", status_code=401)

    # Issue tokens
    access_token = create_access_token(user.id, user.role, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)

    # Store hashed refresh + update last login
    user.refresh_token_hash = hash_password(refresh_token)
    user.last_login_at = datetime.now(UTC)
    await db.flush()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def rotate_refresh_token(
    db: AsyncSession, refresh_token: str
) -> tuple[str, str]:
    """
    Validate a refresh token and issue a new access token + new refresh token.
    Returns (new_access_token, new_refresh_token).
    """
    from apps.api.core.security import decode_token, create_refresh_token, create_access_token

    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise AuthError(str(exc), status_code=401) from exc

    if payload.get("type") != "refresh":
        raise AuthError("Not a refresh token", status_code=401)

    user_id = uuid.UUID(payload["sub"])
    token_version_in_token: int = payload["token_version"]

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive", status_code=401)

    # Check global logout (token_version mismatch)
    if user.token_version != token_version_in_token:
        raise AuthError("Token has been invalidated (global logout)", status_code=401)

    # Check refresh token hash (reuse detection)
    if user.refresh_token_hash is None or not verify_password(
        refresh_token, user.refresh_token_hash
    ):
        # Reuse of a rotated token detected — revoke ALL sessions
        user.token_version += 1
        user.refresh_token_hash = None
        await db.flush()
        raise AuthError(
            "Refresh token reuse detected — all sessions invalidated", status_code=401
        )

    # Issue new access token and new refresh token
    new_access_token = create_access_token(user.id, user.role, user.token_version)
    new_refresh_token = create_refresh_token(user.id, user.token_version)

    # Store hash of new refresh token, invalidate old one
    user.refresh_token_hash = hash_password(new_refresh_token)
    await db.flush()

    return new_access_token, new_refresh_token


async def logout_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    """
    Invalidate all sessions for a user by incrementing token_version.
    Section 13.1: Global logout mechanism.
    """
    user = await db.get(User, user_id)
    if user is not None:
        user.token_version += 1
        user.refresh_token_hash = None
        await db.flush()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> UserOut:
    """Fetch user by ID and return safe schema (no secrets)."""
    user = await db.get(User, user_id)
    if user is None:
        raise AuthError("User not found", status_code=404)
    return UserOut.model_validate(user)
