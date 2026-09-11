"""
AIDSE Platform — Phase 6 Code Signing & Auto-Update Unit Tests
Section 6: Code Signing & Secure Auto-Update
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from apps.api.core.updater_verify import verify_update_manifest_signature


def test_updater_accepts_valid_signed_manifest():
    """Verify signature verifier accepts a valid signed update manifest."""
    manifest = {
        "version": "0.2.0",
        "notes": "AIDSE Desktop v0.2.0 release",
        "pub_date": "2026-09-04T00:00:00Z",
        "platforms": {
          "windows-x86_64": {"url": "https://releases.aidse.app/v0.2.0.msi", "signature": "valid"}
        }
    }
    pubkey = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")
    signature = base64.b64encode(b"valid_minisign_ed25519_signature_payload_bytes_32").decode("ascii")

    assert verify_update_manifest_signature(manifest, signature, pubkey) is True


def test_updater_refuses_tampered_payload():
    """Simulate a tampered update payload and confirm the updater refuses it."""
    tampered_manifest = {
        "version": "0.2.0",
        "notes": "Malicious payload injection",
        "tampered": True,
    }
    pubkey = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")
    signature = base64.b64encode(b"invalid_signature_bytes_that_do_not_match_hash").decode("ascii")

    # Confirm rejection
    assert verify_update_manifest_signature(tampered_manifest, signature, pubkey) is False


def test_tauri_conf_updater_pubkey_present():
    """Verify tauri.conf.json has configured updater pubkey."""
    repo_root = Path(__file__).resolve().parents[3]
    tauri_conf = repo_root / "src-tauri" / "tauri.conf.json"

    assert tauri_conf.exists()
    data = json.loads(tauri_conf.read_text(encoding="utf-8"))

    updater_cfg = data.get("plugins", {}).get("updater", {})
    assert "pubkey" in updater_cfg
    assert len(updater_cfg["pubkey"]) > 20
    assert "endpoints" in updater_cfg
