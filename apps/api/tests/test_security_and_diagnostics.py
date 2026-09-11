"""
AIDSE Platform — Security Hardening & Diagnostics Tests
Validates Path Traversal shielding, DNS Rebinding prevention,
Desktop mode session authorization, and Startup Error logging.
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.core.dependencies import DEFAULT_DESKTOP_USER_ID
from apps.api.core.storage import get_aidse_data_dir, get_storage_root, get_startup_error_log_path


def test_storage_helpers():
    data_dir = get_aidse_data_dir()
    assert data_dir.exists()
    assert data_dir.is_dir()

    storage_root = get_storage_root()
    assert storage_root.exists()
    assert storage_root.is_dir()

    err_log = get_startup_error_log_path()
    assert err_log.name == "startup_error.log"


def test_dns_rebinding_host_header_blocked():
    app = create_app()
    client = TestClient(app)

    # Attack: Attacker sends request with external host header
    resp = client.get("/health", headers={"host": "malicious-site.com"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_HOST"

    # Legitimate: Local loopback host headers allowed
    resp_loopback = client.get("/health", headers={"host": "127.0.0.1:8010"})
    assert resp_loopback.status_code == 200

    resp_localhost = client.get("/health", headers={"host": "localhost:8010"})
    assert resp_localhost.status_code == 200


def test_path_traversal_blocked():
    app = create_app()
    client = TestClient(app)

    # Attempt path traversal across directory boundaries
    resp = client.get("/..%2f..%2fWindows/win.ini")
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_desktop_mode_auto_authorization(client, monkeypatch):
    monkeypatch.setenv("AIDSE_DESKTOP_MODE", "1")

    # In desktop mode without Authorization header, user context is automatically granted
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(DEFAULT_DESKTOP_USER_ID)
    assert data["email"] == "local@aidse.internal"
    assert data["role"] == "admin"
