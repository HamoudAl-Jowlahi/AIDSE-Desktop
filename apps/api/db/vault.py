"""
AIDSE Platform — Per-Install Secret Vault

Holds one 256-bit secret per installation, used to derive the key that
encrypts sensitive column values (see apps/api/core/crypto.py) — today that
is the user's LLM provider API key.

Storage order:
  1. AIDSE_APP_SECRET environment variable (CI, tests, server deployments)
  2. OS-native credential store via `keyring`
     (Windows Credential Manager / macOS Keychain / Linux Secret Service)
  3. A 0600 file inside the AIDSE data directory

Scope, stated plainly: this protects stored secrets from casual inspection of
the database file. It is NOT full-database encryption — the SQLite file itself
is readable. Whole-database encryption would require SQLCipher and a different
driver; it is not implemented, and nothing here should be described as if it
were.
"""
from __future__ import annotations

import logging
import os
import secrets
import stat
from pathlib import Path

logger = logging.getLogger("aidse.vault")

SERVICE_NAME = "AIDSE_Platform_Desktop"
ACCOUNT_NAME = "app_secret"
_SECRET_FILENAME = "app_secret.key"

# Cached so a keyring prompt or file read happens once per process.
_cached_secret: str | None = None


def _secret_file() -> Path:
    from apps.api.core.storage import get_aidse_data_dir

    return get_aidse_data_dir() / _SECRET_FILENAME


def _read_secret_file() -> str | None:
    path = _secret_file()
    if not path.is_file():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    except OSError as exc:
        logger.warning("Could not read the secret file at %s: %s", path, exc)
        return None


def _write_secret_file(secret: str) -> bool:
    """Persist the secret with owner-only permissions. Returns success."""
    path = _secret_file()
    try:
        path.write_text(secret, encoding="utf-8")
        # POSIX: 0600. On Windows the file already sits in the per-user
        # LOCALAPPDATA tree, which other standard users cannot read.
        if os.name != "nt":
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return True
    except OSError as exc:
        logger.error("Could not persist the app secret to %s: %s", path, exc)
        return False


def get_or_create_app_secret() -> str:
    """
    Return this installation's 256-bit hex secret, creating it on first use.

    Never returns a throwaway value: a secret that could not be persisted
    anywhere would silently make every previously encrypted column
    undecryptable on the next launch, so that case raises instead.
    """
    global _cached_secret
    if _cached_secret:
        return _cached_secret

    env_secret = os.getenv("AIDSE_APP_SECRET")
    if env_secret:
        _cached_secret = env_secret
        return _cached_secret

    keyring_available = False
    try:
        import keyring

        keyring_available = True
        existing = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
        if existing:
            _cached_secret = existing
            return _cached_secret
    except ImportError:
        logger.warning(
            "The `keyring` package is not installed, so the app secret cannot "
            "be stored in the OS credential store. Falling back to a file."
        )
    except Exception as exc:  # locked keyring, no backend, D-Bus missing…
        logger.warning("OS credential store unavailable (%s); falling back to a file.", exc)

    file_secret = _read_secret_file()
    if file_secret:
        _cached_secret = file_secret
        return _cached_secret

    new_secret = secrets.token_hex(32)
    stored = False

    if keyring_available:
        try:
            import keyring

            keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, new_secret)
            stored = True
            logger.info("Created a new app secret in the OS credential store.")
        except Exception as exc:
            logger.warning("Could not write to the OS credential store: %s", exc)

    if not stored:
        stored = _write_secret_file(new_secret)
        if stored:
            logger.info("Created a new app secret at %s.", _secret_file())

    if not stored:
        raise RuntimeError(
            "Could not store the application secret in either the OS credential "
            f"store or {_secret_file()}. Refusing to continue with a throwaway "
            "key, which would make saved provider credentials unreadable after "
            "restart. Check the permissions on the AIDSE data directory."
        )

    _cached_secret = new_secret
    return _cached_secret


def reset_cache() -> None:
    """Drop the in-process cache. For tests that swap the backing store."""
    global _cached_secret
    _cached_secret = None
