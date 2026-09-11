"""
AIDSE Platform — Symmetric encryption for stored secrets (Section 13.4)

Fernet (AES-128-CBC + HMAC) keyed from SECRET_KEY via SHA-256, so no extra
key material to manage. Ciphertext is prefixed `enc:v1:` so stored values
are self-describing and legacy plaintext can be migrated transparently.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:v1:"


@lru_cache
def _fernet() -> Fernet:
    from apps.api.core.config import get_settings

    key = hashlib.sha256(get_settings().SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_value(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns `enc:v1:<token>`."""
    token = _fernet().encrypt(plaintext.encode()).decode()
    return f"{_PREFIX}{token}"


def decrypt_value(stored: str) -> str:
    """
    Decrypt a stored secret. Transparently passes through legacy plaintext
    (values written before encryption was introduced) so callers never break.
    """
    if not stored.startswith(_PREFIX):
        return stored  # legacy plaintext — return as-is
    try:
        return _fernet().decrypt(stored[len(_PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Stored secret was encrypted with a different SECRET_KEY — "
            "it cannot be decrypted."
        ) from exc


def is_encrypted(stored: str) -> bool:
    return stored.startswith(_PREFIX)
