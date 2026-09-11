"""
AIDSE Platform — Phase 4 SQLCipher Data Encryption Unit Tests
Section 4: Data Encryption at Rest & OS Secure Storage
"""
from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

from apps.api.db.vault import get_or_create_db_encryption_key, is_database_encrypted_with_key


def test_vault_key_generation_and_retrieval(monkeypatch):
    """Verify get_or_create_db_encryption_key returns a valid 256-bit hex encryption key."""
    test_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    monkeypatch.setenv("AIDSE_DB_ENCRYPTION_KEY", test_key)

    retrieved_key = get_or_create_db_encryption_key()
    assert retrieved_key == test_key
    assert len(retrieved_key) == 64


def test_raw_db_unreadable_without_key():
    """Verify raw encrypted .db file (non-standard SQLite header) is recognized as encrypted."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        # Write random encrypted header bytes (SQLCipher salt/encrypted payload)
        tmp.write(secrets.token_bytes(4096))
        db_path = tmp.name

    try:
        key = "super_secret_master_key_32bytes_len"
        assert is_database_encrypted_with_key(db_path, key) is True
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_plain_db_recognized_as_unencrypted():
    """Verify plain SQLite file with standard header is detected as unencrypted."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(b"SQLite format 3\x00" + b"\x00" * 4000)
        db_path = tmp.name

    try:
        key = "super_secret_master_key_32bytes_len"
        assert is_database_encrypted_with_key(db_path, key) is False
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
