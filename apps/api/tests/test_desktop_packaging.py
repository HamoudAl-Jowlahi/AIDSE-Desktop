"""
AIDSE Platform — Packaging integrity and offline operation

The previous version of this file wrote b"mock_binary_payload" into a temp
directory, deleted it, and asserted the directory was gone; it also measured
numpy allocations and called that "resource profiling". None of it touched the
packaging, so it stayed green while installer.iss shipped an incomplete file
set and the migration runner silently did nothing on every installed machine.

These tests read the real manifests and run the real pipeline instead.
"""
from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


# ── Installer manifest ─────────────────────────────────────────────────────


def _installer_sources() -> list[str]:
    """Every `Source:` path declared in the [Files] section of installer.iss."""
    text = (REPO_ROOT / "installer.iss").read_text(encoding="utf-8")
    files_section = text.split("[Files]", 1)[1].split("[Icons]", 1)[0]
    return re.findall(r'Source:\s*"([^"]+)"', files_section)


def test_every_installer_source_exists_in_the_repo():
    """
    A Source: line pointing at a path that does not exist produces an installer
    missing that file, with no error at build time for anything wildcarded.
    """
    missing = []
    for source in _installer_sources():
        # Trailing \* means "this directory's contents"; check the directory.
        candidate = REPO_ROOT / source.replace("\\*", "").replace("\\", "/")
        if not candidate.exists():
            missing.append(source)

    assert not missing, f"installer.iss references paths that do not exist: {missing}"


def test_installer_ships_the_alembic_config():
    """
    The migration runner resolves alembic.ini next to apps/. Without it in the
    installed tree, run_migrations_headless() finds nothing and returns, which
    is how every install ended up with a create_all schema and no recorded
    revision.
    """
    sources = [s.replace("\\", "/").lower() for s in _installer_sources()]
    assert "alembic.ini" in sources, "installer.iss does not ship alembic.ini"


def test_installer_ships_the_migration_scripts():
    """apps\\api\\* carries db/migrations; assert the versions actually exist."""
    versions = REPO_ROOT / "apps" / "api" / "db" / "migrations" / "versions"
    revisions = [p for p in versions.glob("*.py") if p.name != "__init__.py"]
    assert revisions, "no migration revisions found to package"


def test_installer_does_not_ship_secrets():
    """Signing keys and .env must never reach an end user's machine."""
    forbidden = ("keys", ".env", "private.pem", ".db")
    leaked = [
        s for s in _installer_sources()
        if any(token in s.lower() for token in forbidden)
    ]
    assert not leaked, f"installer.iss would ship secrets or local state: {leaked}"


# ── PyInstaller spec ───────────────────────────────────────────────────────


def test_sidecar_spec_data_paths_exist():
    """
    Each (source, dest) in the spec's `datas` must exist, or the frozen build
    silently omits it. This is what pointed at the deleted apps/api/alembic.
    """
    spec = REPO_ROOT / "infrastructure" / "desktop" / "sidecar.spec"
    if not spec.is_file():
        pytest.skip("sidecar.spec not present")

    text = spec.read_text(encoding="utf-8")
    datas_block = text.split("datas = [", 1)[1].split("]", 1)[0]
    sources = re.findall(r"\(\s*'([^']+)'\s*,", datas_block)

    spec_dir = spec.parent
    missing = [s for s in sources if not (spec_dir / s).resolve().exists()]
    assert not missing, f"sidecar.spec bundles paths that do not exist: {missing}"


# ── Tauri capability allow-list ────────────────────────────────────────────

# Permissions the desktop shell is allowed to hold. Adding anything to
# capabilities/default.json without adding it here fails the test on purpose:
# the point is that widening the shell's authority is a deliberate act.
APPROVED_PERMISSIONS = {
    "core:default",
    "shell:allow-execute",
    "shell:allow-sidecar",
    "process:allow-restart",
    "process:allow-exit",
}


def test_capabilities_stay_within_the_approved_set():
    import json

    cap = json.loads(
        (REPO_ROOT / "src-tauri" / "capabilities" / "default.json").read_text(encoding="utf-8")
    )
    granted = {p for p in cap.get("permissions", []) if isinstance(p, str)}

    unexpected = granted - APPROVED_PERMISSIONS
    assert not unexpected, (
        f"capabilities/default.json grants un-reviewed permissions: {sorted(unexpected)}. "
        "Add them to APPROVED_PERMISSIONS only after deciding the shell needs them."
    )


def test_no_filesystem_or_wildcard_permissions():
    import json

    cap = json.loads(
        (REPO_ROOT / "src-tauri" / "capabilities" / "default.json").read_text(encoding="utf-8")
    )
    for perm in cap.get("permissions", []):
        if not isinstance(perm, str):
            continue
        assert "*" not in perm, f"wildcard permission {perm!r}"
        assert not perm.startswith("fs:"), f"filesystem permission {perm!r} grants disk access"


# ── Offline operation ──────────────────────────────────────────────────────


def test_the_real_profiling_pipeline_makes_no_network_calls(monkeypatch, tmp_path):
    """
    Runs AIDSE's own ingestion → profiling → quality path with every
    non-loopback connect() blocked. The old version of this test fitted a
    RandomForest from scikit-learn instead, which exercised none of this code.
    """
    import pandas as pd

    attempted: list[tuple] = []
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1"):
            attempted.append(address)
            raise OSError(f"offline: blocked connection to {address}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    csv = tmp_path / "sample.csv"
    pd.DataFrame(
        {
            "age": [25, 31, 47, 52, None, 38, 29, 41],
            "income": [30_000, 42_000, 88_000, 95_000, 51_000, 67_000, 39_000, 72_000],
            "city": ["riyadh", "jeddah", "riyadh", "dammam", "jeddah", "riyadh", "dammam", "jeddah"],
            "churn": [0, 0, 1, 1, 0, 1, 0, 1],
        }
    ).to_csv(csv, index=False)

    from apps.api.modules.datasets.ingestion import load_dataframe, sniff_target_candidate
    from apps.api.modules.datasets.profiling import profile_dataset_file
    from apps.api.modules.datasets.quality import build_quality_report

    df = load_dataframe(str(csv), ".csv")
    assert len(df) == 8

    profile = profile_dataset_file(str(csv))
    assert profile.get("num_rows") == 8
    assert "columns" in profile

    report = build_quality_report(profile)
    assert report is not None

    candidate = sniff_target_candidate(df)
    assert candidate is not None

    assert not attempted, f"pipeline attempted outbound connections: {attempted}"


def test_llm_narration_is_off_by_default():
    """
    Nothing may leave the machine unless the user configures a provider.
    LLM_PROVIDER defaults to "none" and the guard requires both a provider
    and a key.
    """
    from apps.api.core.config import Settings
    from apps.api.modules.datasets.recommendations import _llm_configured

    defaults = Settings(_env_file=None)
    assert defaults.LLM_PROVIDER == "none"
    assert not _llm_configured(defaults)

    # A provider without a key must still stay offline.
    assert not _llm_configured(Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY=""))
    # Both present is the only configuration that enables egress.
    assert _llm_configured(Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY="sk-x"))
