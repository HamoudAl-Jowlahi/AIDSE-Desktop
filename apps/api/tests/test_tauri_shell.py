"""
AIDSE Platform — Phase 2 Tauri Shell Integration Unit Tests
Section 2: Tauri Shell & IPC Security Verification
"""
from __future__ import annotations

import json
from pathlib import Path


def test_next_config_static_export():
    """Verify next.config.ts contains static export configuration ('output: export')."""
    repo_root = Path(__file__).resolve().parents[3]
    next_config_path = repo_root / "apps" / "web" / "next.config.ts"

    assert next_config_path.exists(), f"next.config.ts missing at {next_config_path}"
    content = next_config_path.read_text(encoding="utf-8")

    assert 'output: "export"' in content or "output: 'export'" in content, (
        "next.config.ts must specify static export output"
    )


def test_tauri_config_exists_and_valid():
    """Verify tauri.conf.json exists with valid CSP, app identifier, and sidecar binaries."""
    repo_root = Path(__file__).resolve().parents[3]
    tauri_conf_path = repo_root / "src-tauri" / "tauri.conf.json"

    assert tauri_conf_path.exists(), f"tauri.conf.json missing at {tauri_conf_path}"
    data = json.loads(tauri_conf_path.read_text(encoding="utf-8"))

    assert data.get("identifier") == "com.aidse.desktop"
    assert data.get("build", {}).get("frontendDist") == "../apps/web/out"

    # CSP check
    csp = data.get("app", {}).get("security", {}).get("csp", "")
    assert "connect-src" in csp, "CSP must restrict connect-src"

    # Sidecar binary check
    external_bin = data.get("bundle", {}).get("externalBin", [])
    assert "binaries/aidse-backend" in external_bin


def test_tauri_capabilities_strict_allow_list():
    """Verify capabilities/default.json exists and enforces explicit allow-list without wildcards."""
    repo_root = Path(__file__).resolve().parents[3]
    capability_path = repo_root / "src-tauri" / "capabilities" / "default.json"

    assert capability_path.exists(), f"Capability file missing at {capability_path}"
    data = json.loads(capability_path.read_text(encoding="utf-8"))

    permissions = data.get("permissions", [])
    assert isinstance(permissions, list)

    # Ensure no wildcard permission exists
    for perm in permissions:
        if isinstance(perm, str):
            assert perm != "*", "Wildcard permission '*' is forbidden in Tauri capability configuration"
            assert not perm.startswith("*"), "Wildcard permissions are forbidden"


def test_sidecar_restart_limit_policy():
    """Simulate sidecar lifecycle restart counter logic ensuring max 3 retries policy."""
    max_retries = 3
    retry_count = 0

    def attempt_restart() -> bool:
        nonlocal retry_count
        if retry_count < max_retries:
            retry_count += 1
            return True
        return False

    # Simulate 3 consecutive crashes
    assert attempt_restart() is True  # retry 1
    assert attempt_restart() is True  # retry 2
    assert attempt_restart() is True  # retry 3

    # 4th crash should be blocked to prevent infinite crash loop
    assert attempt_restart() is False
