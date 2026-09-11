"""
AIDSE Platform — JWT & Password Security Utilities
Section 13.1 (JWT), Section 13.4 (Encryption), Section 23.4 (Coding Standards)

Security decisions documented here per Section 23.2 Rule 4:

- RS256 (asymmetric): public key shareable with downstream services.
- token_version in JWT: incrementing DB value invalidates all issued tokens.
- Refresh token reuse detection: stored hashed; reuse triggers global revocation.
- bcrypt cost factor ≥ 12 per Section 13.4 requirement.
- SHA-256 prehash before bcrypt: handles arbitrary-length inputs (JWT tokens,
  long passwords) without hitting bcrypt's 72-byte limit.

Note: We use bcrypt directly (not passlib) to avoid passlib's incompatibility
with bcrypt v5+ which enforces the 72-byte limit during its own backend detection.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt_lib
from jose import JWTError, jwt

from apps.api.core.config import get_settings

settings = get_settings()
_BCRYPT_ROUNDS: int = settings.BCRYPT_ROUNDS

# ── Password / Secret Hashing ──────────────────────────────────────────────


def _pre_hash(value: str) -> bytes:
    """SHA-256 prehash — returns 32 raw bytes, safely under bcrypt's 72-byte limit.

    Used for all inputs to hash_password / verify_password so that:
    - Long passwords are handled correctly (full entropy preserved)
    - JWT refresh tokens (~180 chars) can be stored hashed safely
    """
    return hashlib.sha256(value.encode()).digest()


def hash_password(secret: str) -> str:
    """Hash a secret (password or token) with bcrypt (cost ≥ 12).

    SHA-256 prehash applied first to support arbitrary-length inputs.
    Returns a bcrypt hash string (60 chars, starts with $2b$).
    """
    salt = _bcrypt_lib.gensalt(rounds=_BCRYPT_ROUNDS)
    return _bcrypt_lib.hashpw(_pre_hash(secret), salt).decode()


def verify_password(plain_secret: str, hashed_secret: str) -> bool:
    """Verify a secret against its bcrypt hash.

    Applies the same SHA-256 prehash used at hash time.
    Returns False (never raises) on any verification failure.
    """
    try:
        return _bcrypt_lib.checkpw(_pre_hash(plain_secret), hashed_secret.encode())
    except Exception:
        return False


# ── JWT ────────────────────────────────────────────────────────────────────

ALGORITHM = "RS256"
TOKEN_TYPE = "Bearer"


def _get_private_key() -> str:
    return settings.jwt_private_key_pem


def _get_public_key() -> str:
    return settings.jwt_public_key_pem


def create_access_token(
    user_id: uuid.UUID,
    role: str,
    token_version: int,
) -> str:
    """Create a short-lived RS256 access token.

    Claims per Section 13.1:
    - sub: user UUID string
    - role: system role
    - token_version: global logout sentinel
    - type: "access"
    - exp: 15 minutes from now (configurable)
    - jti: unique token ID for replay prevention
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "token_version": token_version,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _get_private_key(), algorithm=ALGORITHM)


def create_refresh_token(
    user_id: uuid.UUID,
    token_version: int,
) -> str:
    """Create a longer-lived RS256 refresh token.

    Carries token_version to detect reuse of a rotated token.
    Stored hashed in DB; invalidated on every use.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "token_version": token_version,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _get_private_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Returns the payload dict on success.
    Raises JWTError (converted to 401 by callers) on failure.
    """
    try:
        return jwt.decode(token, _get_public_key(), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise JWTError(f"Invalid or expired token: {exc}") from exc
