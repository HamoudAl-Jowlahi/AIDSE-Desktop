"""
AIDSE Platform — Symmetric encryption for stored secrets (Section 13.4)

Fernet (AES-128-CBC + HMAC). The key is derived from the per-install secret
held in apps/api/db/vault.py, so each installation encrypts with material
that exists only on that machine.

Values are prefixed `enc:v1:` so stored data is self-describing and legacy
plaintext migrates transparently.

Legacy note: earlier builds derived the key from Settings.SECRET_KEY, which in
desktop mode was the shipped default "change-me-in-production" — i.e. a key
anyone could reproduce. Those values still decrypt through the legacy fallback
below and are re-encrypted with the real key the next time they are written.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("aidse.crypto")

_PREFIX = "enc:v1:"


def _fernet_from(material: str) -> Fernet:
    key = hashlib.sha256(material.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


@lru_cache
def _fernet() -> Fernet:
    """Primary cipher, keyed from this installation's own secret."""
    from apps.api.db.vault import get_or_create_app_secret

    return _fernet_from(get_or_create_app_secret())


@lru_cache
def _legacy_fernet() -> Fernet:
    """Cipher for values written before the vault-backed key existed."""
    from apps.api.core.config import get_settings

    return _fernet_from(get_settings().SECRET_KEY)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns `enc:v1:<token>`."""
    token = _fernet().encrypt(plaintext.encode()).decode()
    return f"{_PREFIX}{token}"


def decrypt_value(stored: str) -> str:
    """
    Decrypt a stored secret.

    Passes legacy plaintext through unchanged, and falls back to the old
    SECRET_KEY-derived cipher for values written by earlier builds.
    """
    if not stored.startswith(_PREFIX):
        return stored  # legacy plaintext — return as-is

    token = stored[len(_PREFIX):].encode()
    try:
        return _fernet().decrypt(token).decode()
    except InvalidToken:
        pass

    try:
        value = _legacy_fernet().decrypt(token).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Stored secret cannot be decrypted with this installation's key. "
            "It was most likely encrypted on a different machine — re-enter it "
            "in Settings to store it again."
        ) from exc

    logger.info("Decrypted a secret using the legacy key; it will be re-encrypted on next save.")
    return value


def is_encrypted(stored: str) -> bool:
    return stored.startswith(_PREFIX)


def reset_cache() -> None:
    """Drop cached ciphers. For tests that swap the underlying key material."""
    _fernet.cache_clear()
    _legacy_fernet.cache_clear()
