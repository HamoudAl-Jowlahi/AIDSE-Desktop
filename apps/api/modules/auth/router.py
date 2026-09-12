"""
AIDSE Platform — Auth Module Router
Section 11.2 (Auth API endpoints), Section 23.4 (Coding Standards)

Endpoints:
  POST /auth/register  — Register new user, receive tokens
  POST /auth/login     — Authenticate, receive tokens
  POST /auth/refresh   — Rotate refresh token, get new access token
  POST /auth/logout    — Invalidate session, clear refresh cookie
  GET  /auth/me        — Get current user profile (requires auth)

Rate limiting applied to auth endpoints (Section 13.6):
  - /register + /login: aggressive IP-based limit (brute force prevention)
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.api.core.dependencies import get_current_user
from apps.api.db.session import get_db
from apps.api.modules.auth import service
from apps.api.modules.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from apps.api.core.crypto import decrypt_value, encrypt_value
from apps.api.core.config import get_settings
from apps.api.core.rate_limit import limiter
from apps.api.modules.auth.service import AuthError, DuplicateEmailError

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _auth_error_to_http(exc: AuthError) -> HTTPException:
    """Convert domain AuthError to HTTPException with standard error format."""
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": {"code": "AUTH_ERROR", "message": str(exc)}},
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Create a new AIDSE user account. Returns access and refresh tokens. "
        "Email must be unique across the platform."
    ),
)
@limiter.limit("5/minute")
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """POST /api/v1/auth/register — Section 11.2"""
    try:
        tokens = await service.register_user(db, payload)
        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens.refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/api/v1/auth",
        )
        # Return access token only in body; refresh token is in HttpOnly cookie
        return TokenResponse(access_token=tokens.access_token, refresh_token="")
    except DuplicateEmailError as exc:
        from apps.api.modules.auth.router import _auth_error_to_http
        raise _auth_error_to_http(exc) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive tokens",
    description="Validate email+password credentials and receive JWT tokens.",
)
@limiter.limit("5/minute")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """POST /api/v1/auth/login — Section 11.2"""
    try:
        tokens = await service.authenticate_user(db, payload)
        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens.refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/api/v1/auth",
        )
        # Return access token only in body; refresh token is in HttpOnly cookie
        return TokenResponse(access_token=tokens.access_token, refresh_token="")
    except AuthError as exc:
        from apps.api.modules.auth.router import _auth_error_to_http
        raise _auth_error_to_http(exc) from exc


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description=(
        "Exchange a valid refresh token for a new access token. "
        "The refresh token is rotated — reuse of a previous token triggers "
        "global session revocation (Section 13.1)."
    ),
)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest = Body(None),
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    """POST /api/v1/auth/refresh — Section 11.2"""
    from apps.api.modules.auth.service import AuthError
    
    try:
        # Read refresh token from cookie first, fallback to request body
        refresh_token = request.cookies.get("refresh_token") or payload.refresh_token
        if not refresh_token:
            raise AuthError("Refresh token missing", status_code=401)
        
        new_access_token, new_refresh_token = await service.rotate_refresh_token(db, refresh_token)
        
        # Set new refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/api/v1/auth",
        )
        # Return new access token only; refresh token is in HttpOnly cookie
        return AccessTokenResponse(access_token=new_access_token, token_type="Bearer")
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(str(exc), status_code=400) from exc
        from apps.api.modules.auth.router import _auth_error_to_http
        raise _auth_error_to_http(exc) from exc


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout and invalidate session",
    description="Invalidate the current session by clearing the refresh token cookie and invalidating the refresh token in the database.",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    """POST /api/v1/auth/logout — Invalidate session and clear refresh token cookie."""
    # Try to get refresh token from cookie to invalidate it in DB
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        # Invalidate the refresh token in DB
        try:
            from apps.api.modules.auth.service import rotate_refresh_token
            await service.rotate_refresh_token(db, request.cookies.get("refresh_token", ""))
        except Exception:
            pass  # Best effort - token might be invalid already
    
    # Clear the refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        secure=True,
    )


@router.get(
    "/me",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Returns the authenticated user's profile. Requires a valid access token.",
)
async def get_me(
    current_user: UserOut = Depends(get_current_user),
) -> UserOut:
    """GET /api/v1/auth/me — Section 11.2"""
    return current_user


from pydantic import BaseModel, Field


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(default="", description="Current password if previously set")
    # Empty clears the lock. Anything else must be at least 6 characters —
    # validated in the handler so "remove it" stays expressible.
    new_password: str = Field(..., description="New password, or empty to remove the lock")


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    summary="Change application access password",
    description="Update password for current desktop/authenticated user.",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from apps.api.modules.auth.models import User
    from apps.api.core.security import hash_password, verify_password
    from sqlalchemy import update

    res = await db.execute(select(User).where((User.id == current_user.id) | (User.email == current_user.email)))
    user_record = res.scalar_one_or_none()
    if not user_record:
        raise HTTPException(status_code=404, detail="User record not found")

    is_default = (user_record.password_hash == "local_desktop_unrestricted_session")
    if not is_default:
        if not payload.current_password:
            raise HTTPException(status_code=400, detail="Please enter the current password")
        if not verify_password(payload.current_password, user_record.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    if payload.new_password == "":
        # Remove the lock and return to the unrestricted local session.
        new_hash = "local_desktop_unrestricted_session"
        message = "Lock removed. AIDSE will open without a password."
    elif len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    else:
        new_hash = hash_password(payload.new_password)
        message = "Password updated successfully"

    await db.execute(
        update(User)
        .where((User.id == current_user.id) | (User.email == current_user.email))
        .values(password_hash=new_hash)
    )
    await db.commit()
    return {"status": "ok", "message": message}


class VerifyPasswordPayload(BaseModel):
    password: str = Field(..., description="Application password to verify")


@router.post(
    "/verify-password",
    status_code=status.HTTP_200_OK,
    summary="Verify application access password",
    description="Validates entered password for unlocking the local workspace.",
)
@limiter.limit(get_settings().RATE_LIMIT_AUTH)
async def verify_app_password(
    request: Request,
    payload: VerifyPasswordPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from apps.api.modules.auth.models import User
    from apps.api.core.security import verify_password

    res = await db.execute(select(User).limit(1))
    user_record = res.scalar_one_or_none()
    if not user_record or user_record.password_hash == "local_desktop_unrestricted_session":
        return {"valid": True, "message": "No password configured"}

    if not verify_password(payload.password, user_record.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password. Please try again.")

    return {"valid": True, "message": "Password verified successfully"}


@router.get(
    "/has-password",
    status_code=status.HTTP_200_OK,
    summary="Check if master password is set",
)
async def check_has_password(
    db: AsyncSession = Depends(get_db),
) -> dict:
    from apps.api.modules.auth.models import User

    res = await db.execute(select(User).limit(1))
    user_record = res.scalar_one_or_none()
    has_pass = bool(user_record and user_record.password_hash and user_record.password_hash != "local_desktop_unrestricted_session")
    return {"has_password": has_pass}