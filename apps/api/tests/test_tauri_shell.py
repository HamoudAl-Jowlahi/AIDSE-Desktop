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

        Failed to load Python DLL ..._internal/python314.dll

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


def _updater() -> dict | None:
    return _tauri_conf().get("plugins", {}).get("updater")


def test_updater_points_at_the_github_release_manifest():
    """
    The endpoint is the whole update mechanism: it decides which file the app
    trusts to tell it a newer version exists. It must be https — over http a
    network attacker chooses the version, and while the signature check would
    still refuse a forged installer, a downgrade manifest could pin users to
    an old build forever.
    """
    updater = _updater()
    if not updater:
        pytest.skip("updater not configured")

    endpoints = updater.get("endpoints") or []
    assert endpoints, "updater configured without endpoints"

    for url in endpoints:
        assert url.startswith("https://"), f"update endpoint is not https: {url}"
        assert url.endswith(".json"), (
            f"update endpoint must serve a manifest, got {url}"
        )


def test_updater_public_key_is_a_real_minisign_key():
    """
    The shipped config once declared a minisign public key that decoded to 18
    bytes; a real one is 42. A malformed key means signature verification can
    never succeed, so the updater silently stops working.

    An empty key is the honest "not generated yet" state and skips — the key
    is generated by hand and pasted in, because the private half must never
    pass through a build or a repository.
    """
    import base64

    updater = _updater()
    if not updater:
        pytest.skip("updater not configured")

    pubkey = updater.get("pubkey", "")
    if not pubkey:
        pytest.skip(
            "no signing keypair yet — run `npm run tauri signer generate` and "
            "paste the public key into plugins.updater.pubkey (docs/releasing.md)"
        )

    decoded = base64.b64decode(pubkey)
    key_line = decoded.decode("utf-8", "replace").splitlines()[-1]
    key_bytes = base64.b64decode(key_line + "==")

    assert len(key_bytes) == 42, (
        f"minisign public key decodes to {len(key_bytes)} bytes, expected 42 — "
        "the updater cannot verify signatures with this key."
    )


def test_the_page_is_allowed_to_run_the_updater():
    """
    Capabilities gate what the webview may ask Rust to do. Without
    updater:default the check silently fails with a permission error, and
    without process:allow-restart the app installs an update and then sits
    there on the old version.
    """
    if not _updater():
        pytest.skip("updater not configured")

    caps = json.loads(
        (TAURI / "capabilities" / "default.json").read_text(encoding="utf-8")
    )
    permissions = caps.get("permissions", [])

    assert "updater:default" in permissions, (
        "the updater is configured but the window may not call it"
    )
    assert "process:allow-restart" in permissions, (
        "nothing can relaunch the app after an update installs"
    )


def test_release_workflow_is_where_github_will_find_it():
    """
    infrastructure/github-actions/ci.yml is server-era leftovers that GitHub
    never runs, because workflows are only picked up from .github/workflows.
    The release workflow must not repeat that.
    """
    workflow = REPO_ROOT / ".github" / "workflows" / "release.yml"
    assert workflow.is_file(), "no release workflow in .github/workflows"

    body = workflow.read_text(encoding="utf-8")
    assert "includeUpdaterJson: true" in body, (
        "the workflow does not publish latest.json, so the configured endpoint "
        "would 404 and no update could ever be found"
    )
    assert "TAURI_SIGNING_PRIVATE_KEY" in body, (
        "the workflow does not sign the installer; unsigned builds are refused "
        "by every installed copy"
    )


def test_the_private_signing_key_is_not_in_the_repository():
    """
    A committed private key lets anyone sign an installer the app will trust
    and run. Cheap to check, catastrophic to miss.
    """
    suspects = [
        p
        for p in REPO_ROOT.rglob("*.key")
        if ".git" not in p.parts and "node_modules" not in p.parts
    ]
    leaked = [
        p
        for p in suspects
        if "untrusted comment: minisign encrypted secret key"
        in p.read_text(encoding="utf-8", errors="ignore").lower()
    ]
    assert not leaked, f"minisign private key committed: {leaked}"


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
