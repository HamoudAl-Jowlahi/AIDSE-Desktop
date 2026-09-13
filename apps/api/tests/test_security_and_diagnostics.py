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

REPO_ROOT = Path(__file__).resolve().parents[3]


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


# ── The shipped entry point refuses to run unprotected ─────────────────────


def test_sidecar_entry_requires_an_internal_token():
    """
    sidecar_entry.py is the only entry point that ships. The backend listens
    on loopback, which every process running as this user can reach, so a
    missing token means the API is open to all of them.

    It used to accept a missing token because the Edge launcher opened a plain
    browser window, which cannot attach a custom header. That launcher is gone.
    """
    source = (REPO_ROOT / "apps" / "api" / "sidecar_entry.py").read_text(encoding="utf-8")

    assert "if not args.token:" in source, (
        "sidecar_entry.py no longer checks for a missing token"
    )
    guard = source.split("if not args.token:", 1)[1][:600]
    assert "SystemExit" in guard, (
        "a missing token must stop startup, not just warn: the app would run "
        "reachable by any local process"
    )


def test_launch_on_startup_never_registers_the_backend():
    """
    The registry entry has to point at the shell. The backend on its own has
    no window, no token and no supervisor, so registering it would give the
    user a headless 390 MB process at every login and no application.

    This is what the code did once Launch-AIDSE.vbs was deleted: the lookup
    fell through to sys.executable, which inside the bundle is the backend.
    """
    source = (REPO_ROOT / "apps" / "api" / "modules" / "system" / "router.py").read_text(
        encoding="utf-8"
    )
    block = source.split("def _set_startup_registry", 1)[1].split("\n@router", 1)[0]

    assert "_find_shell_executable" in block, (
        "the startup entry is not resolved through the shell lookup"
    )

    # What is written to the registry is the only thing that matters here.
    # sys.executable appearing in a log message is fine; appearing in the
    # value written is the bug.
    written = [
        line for line in block.splitlines() if "SetValueEx" in line
    ]
    assert written, "nothing is written to the Run key any more"
    for line in written:
        assert "sys.executable" not in line, (
            f"the startup entry is set from sys.executable, which inside the "
            f"bundle is the backend, not the shell: {line.strip()}"
        )
        assert "shell" in line, (
            f"the startup entry is not set from the resolved shell path: {line.strip()}"
        )
    # Naming the launcher in a comment, to say why it is gone, is not the
    # same as looking for it. Only executable lines count.
    live = [
        line for line in source.splitlines()
        if "Launch-AIDSE" in line and not line.lstrip().startswith("#")
    ]
    assert not live, f"still looking for the deleted Edge launcher: {live}"
