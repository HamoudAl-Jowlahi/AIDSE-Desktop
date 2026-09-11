"""
AIDSE Platform — Stored-secret encryption tests

Replaces the former test_sqlcipher_encryption.py, which asserted that a file
of random bytes did not start with the SQLite magic header. That passed no
matter what the application did, and it passed for the entire period during
which the shipped database was plaintext.

These tests exercise the real path instead: the vault that holds the
per-install secret, and the cipher that protects provider API keys. Each one
fails if the protection it covers is removed.
"""
from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.fernet import Fernet

from apps.api.core import crypto
from apps.api.db import vault


@pytest.fixture(autouse=True)
def _isolated_secret(monkeypatch, tmp_path):
    """Give every test its own app secret and a clean cipher cache."""
    monkeypatch.setenv("AIDSE_APP_SECRET", "a" * 64)
    vault.reset_cache()
    crypto.reset_cache()
    yield
    vault.reset_cache()
    crypto.reset_cache()


# ── Vault ──────────────────────────────────────────────────────────────────


def test_app_secret_is_256_bit_and_stable():
    secret = vault.get_or_create_app_secret()
    assert len(secret) == 64
    assert secret == vault.get_or_create_app_secret(), "secret must not change between calls"


def test_generated_secret_is_persisted_not_thrown_away(monkeypatch, tmp_path):
    """
    A secret that is generated but never stored would make every encrypted
    column unreadable after restart. The vault must persist or raise.
    """
    monkeypatch.delenv("AIDSE_APP_SECRET", raising=False)
    monkeypatch.setenv("AIDSE_DATA_DIR", str(tmp_path))
    monkeypatch.setitem(__import__("sys").modules, "keyring", None)  # force file fallback
    vault.reset_cache()

    first = vault.get_or_create_app_secret()
    assert (tmp_path / "app_secret.key").is_file(), "secret was not written to disk"

    vault.reset_cache()
    second = vault.get_or_create_app_secret()
    assert first == second, "secret did not survive a process restart"


def test_vault_raises_rather_than_returning_a_throwaway_key(monkeypatch, tmp_path):
    monkeypatch.delenv("AIDSE_APP_SECRET", raising=False)
    monkeypatch.setenv("AIDSE_DATA_DIR", str(tmp_path))
    monkeypatch.setitem(__import__("sys").modules, "keyring", None)
    monkeypatch.setattr(vault, "_write_secret_file", lambda secret: False)
    vault.reset_cache()

    with pytest.raises(RuntimeError, match="Refusing to continue"):
        vault.get_or_create_app_secret()


# ── Cipher ─────────────────────────────────────────────────────────────────


def test_encrypted_value_does_not_contain_the_plaintext():
    secret = "sk-proj-9f3a2b1c-do-not-leak"
    blob = crypto.encrypt_value(secret)

    assert blob.startswith("enc:v1:")
    assert secret not in blob
    assert crypto.decrypt_value(blob) == secret


def test_ciphertext_is_not_reproducible_from_the_default_secret_key():
    """
    Earlier builds derived the key from the shipped default SECRET_KEY
    ("change-me-in-production"), so anyone could decrypt a stolen database.
    The active key must not be derivable that way.
    """
    blob = crypto.encrypt_value("sk-live-secret")
    default_cipher = Fernet(
        base64.urlsafe_b64encode(hashlib.sha256(b"change-me-in-production").digest())
    )

    with pytest.raises(Exception):
        default_cipher.decrypt(blob[len("enc:v1:"):].encode())


def test_values_from_another_installation_fail_loudly():
    foreign = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"other-machine").digest()))
    blob = "enc:v1:" + foreign.encrypt(b"whatever").decode()

    with pytest.raises(ValueError, match="different machine"):
        crypto.decrypt_value(blob)


def test_legacy_secret_key_values_still_decrypt(monkeypatch):
    """Rows written before the vault existed must keep working after upgrade."""
    legacy_blob = "enc:v1:" + crypto._legacy_fernet().encrypt(b"older-api-key").decode()
    assert crypto.decrypt_value(legacy_blob) == "older-api-key"


def test_pre_encryption_plaintext_passes_through():
    assert crypto.decrypt_value("plain-old-value") == "plain-old-value"


# ── Honesty guard ──────────────────────────────────────────────────────────


def test_no_code_claims_sqlcipher_whole_database_encryption():
    """
    Whole-database encryption is not implemented. This guard fails if the
    claim is reintroduced into the database layer, which is how the previous
    documentation drifted away from reality.
    """
    import io
    import tokenize
    from pathlib import Path

    def executable_source(path: Path) -> str:
        """Source with comments and docstrings stripped, so prose about the
        old behaviour does not trip the guard."""
        kept: list[str] = []
        prev_type = tokenize.INDENT
        with open(path, "rb") as handle:
            for tok in tokenize.tokenize(handle.readline):
                if tok.type == tokenize.COMMENT:
                    continue
                if tok.type == tokenize.STRING and prev_type in (
                    tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, tokenize.ENCODING,
                ):
                    continue  # docstring
                kept.append(tok.string)
                if tok.type not in (tokenize.NL, tokenize.COMMENT):
                    prev_type = tok.type
        return "\n".join(kept)

    db_layer = Path(__file__).resolve().parents[1] / "db"
    offenders = [
        path.name
        for path in db_layer.glob("*.py")
        if "PRAGMA key" in executable_source(path)
    ]
    assert not offenders, (
        f"{offenders} sets `PRAGMA key`, which is a silent no-op on stdlib "
        "sqlite3 and produces a plaintext database."
    )
