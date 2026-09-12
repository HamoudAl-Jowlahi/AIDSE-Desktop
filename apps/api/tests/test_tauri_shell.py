"""
AIDSE Platform — Desktop shell configuration

These assert on the shell's build and security configuration, which is all
Python can reach: the shell itself is Rust. The previous version of this file
ended with a "sidecar restart limit" test that defined its own counter function
inside the test body and asserted against that — SidecarManager was never
imported. The real policy is now covered by a Rust unit test in
src-tauri/src/sidecar_manager.rs.

Note on scope: these cover configuration, not runtime. The shell itself now
spawns the backend and generates a per-launch token — that behaviour is
verified by the Rust tests and by running the packaged binary.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB = REPO_ROOT / "apps" / "web"
TAURI = REPO_ROOT / "src-tauri"


def _tauri_conf() -> dict:
    return json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))


# ── Frontend build ─────────────────────────────────────────────────────────


def _next_config_source() -> str:
    """
    next.config.ts with comments stripped.

    Without this, commenting a setting out still satisfies a regex looking for
    it — which is exactly how the first version of this test let a disabled
    `output: "export"` pass.
    """
    raw = (WEB / "next.config.ts").read_text(encoding="utf-8")
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)      # block comments
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)   # whole-line comments
    return re.sub(r"//.*$", "", raw, flags=re.MULTILINE)      # trailing comments


def test_next_is_configured_for_static_export():
    """Tauri serves files from disk; a server-rendered build would not load."""
    assert re.search(r'output:\s*["\']export["\']', _next_config_source()), (
        "next.config.ts must set output: 'export'"
    )


def test_build_does_not_silently_ignore_type_and_lint_errors():
    """
    ignoreBuildErrors / ignoreDuringBuilds let a broken build ship green.
    tsc is clean today, so there is no reason to keep the escape hatch open.
    """
    content = _next_config_source()

    for flag in ("ignoreBuildErrors", "ignoreDuringBuilds"):
        match = re.search(rf"{flag}:\s*(true|false)", content)
        if match:
            assert match.group(1) == "false", (
                f"next.config.ts sets {flag}: true, so the production build "
                "ignores errors that tsc and eslint would catch."
            )


def test_static_export_output_is_what_the_backend_serves():
    """
    main.py falls back to serving apps/web/out when the shell is not used.
    Skipped when the export has not been built (out/ is not in the repo).
    """
    index = WEB / "out" / "index.html"
    if not index.is_file():
        pytest.skip("apps/web/out not built in this checkout")
    assert (WEB / "out" / "_next").is_dir(), "static export is missing its _next assets"


# ── Tauri configuration ────────────────────────────────────────────────────


def test_tauri_identity_and_frontend_path():
    data = _tauri_conf()
    assert data.get("identifier") == "com.aidse.desktop"
    assert data.get("build", {}).get("frontendDist") == "../apps/web/out"


def test_backend_ships_as_a_resource_tree_not_a_single_binary():
    """
    The config used to declare externalBin: binaries/aidse-backend, which cannot
    work. externalBin copies one file, and PyInstaller produces a directory: a
    60 MB launcher stub plus a 790 MB _internal tree holding the Python DLL it
    loads at startup. Running the stub alone fails with

        Failed to load Python DLL ..._internal\python314.dll

    so the bundled app would have had no backend at all.
    """
    bundle = _tauri_conf().get("bundle", {})

    assert "externalBin" not in bundle, (
        "externalBin ships a single file; the PyInstaller backend is a directory"
    )

    resources = bundle.get("resources", {})
    assert resources, "the backend must be bundled as a resource tree"
    assert any("aidse-backend" in src for src in resources), (
        f"no backend entry among the bundled resources: {resources}"
    )


def _csp_directive(csp: str, name: str) -> list[str]:
    for part in csp.split(";"):
        tokens = part.strip().split()
        if tokens and tokens[0] == name:
            return tokens[1:]
    return []


def test_csp_confines_network_access_to_loopback():
    """
    connect-src decides where the page may send data. Anything beyond 'self'
    and loopback would let a compromised page exfiltrate the user's datasets.
    """
    csp = _tauri_conf().get("app", {}).get("security", {}).get("csp", "")
    assert csp, "no CSP configured"

    connect = _csp_directive(csp, "connect-src")
    assert connect, "CSP must set connect-src explicitly"

    allowed = {"'self'", "http://127.0.0.1:*", "ws://127.0.0.1:*"}
    unexpected = [src for src in connect if src not in allowed]
    assert not unexpected, f"connect-src allows non-loopback destinations: {unexpected}"


def test_csp_does_not_allow_remote_scripts():
    csp = _tauri_conf().get("app", {}).get("security", {}).get("csp", "")
    script = _csp_directive(csp, "script-src")
    remote = [s for s in script if s.startswith("http://") or s.startswith("https://")]
    assert not remote, f"script-src permits remote code: {remote}"


def test_updater_is_absent_or_carries_a_real_key():
    """
    The shipped config declared a minisign public key that decoded to 18 bytes;
    a real one is 42. A malformed key means the updater cannot verify anything,
    so it must be either properly configured or not configured at all.
    """
    import base64

    updater = _tauri_conf().get("plugins", {}).get("updater")
    if not updater:
        pytest.skip("updater not configured (removed until a real keypair exists)")

    pubkey = updater.get("pubkey", "")
    decoded = base64.b64decode(pubkey)
    key_line = decoded.decode("utf-8", "replace").splitlines()[-1]
    key_bytes = base64.b64decode(key_line + "==")

    assert len(key_bytes) == 42, (
        f"minisign public key decodes to {len(key_bytes)} bytes, expected 42 — "
        "the updater cannot verify signatures with this key."
    )
    assert updater.get("endpoints"), "updater configured without endpoints"


# ── Rust-side coverage ─────────────────────────────────────────────────────


def test_sidecar_restart_policy_has_a_rust_test():
    """
    The restart limit lives in Rust and cannot be exercised from Python. This
    asserts the Rust test exists, so deleting it is a visible change rather
    than a silent loss of coverage.
    """
    source = (TAURI / "src" / "sidecar_manager.rs").read_text(encoding="utf-8")
    assert "#[cfg(test)]" in source, "sidecar_manager.rs has no test module"
    assert "fn should_restart_stops_after_max_retries" in source, (
        "the restart-limit test is missing from sidecar_manager.rs"
    )
