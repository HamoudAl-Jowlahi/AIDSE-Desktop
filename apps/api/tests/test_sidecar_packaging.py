"""
AIDSE Platform — Phase 1 Packaging Strategy Unit Tests
Section 1: Desktop Shell Integration & Sidecar Packaging
"""
from __future__ import annotations

import os
from pathlib import Path
from apps.api.sidecar_entry import parse_args


def test_sidecar_parse_args_defaults():
    """
    With no --port, the parser yields None rather than 8010.

    That distinction carries weight: an explicitly requested port means the
    caller has already told something else to expect it — the Tauri shell hands
    the same number to its window — so main() binds it or exits. Only when no
    port was asked for does it fall back to scanning from 8010.
    """
    args = parse_args([])
    assert args.host == os.getenv("APP_HOST", "127.0.0.1")
    assert args.port is None, "an unspecified port must stay distinguishable from a chosen one"
    assert args.token == ""


def test_explicit_port_is_taken_literally():
    assert parse_args(["--port", "54321"]).port == 54321


def test_sidecar_parse_args_custom():
    """Verify sidecar_entry parses custom command line arguments."""
    custom_args = ["--host", "127.0.0.1", "--port", "9876", "--token", "secret_test_token"]
    args = parse_args(custom_args)
    assert args.host == "127.0.0.1"
    assert args.port == 9876
    assert args.token == "secret_test_token"


def test_sidecar_spec_exists_and_valid():
    """Verify PyInstaller sidecar spec file exists and includes critical hidden imports."""
    repo_root = Path(__file__).resolve().parents[3]
    spec_path = repo_root / "infrastructure" / "desktop" / "sidecar.spec"

    assert spec_path.exists(), f"Sidecar spec not found at {spec_path}"

    content = spec_path.read_text(encoding="utf-8")
    required_hiddenimports = [
        "uvicorn.logging",
        "sqlalchemy.dialects.sqlite",
        "alembic",
        "optuna",
        "shap",
        "xgboost",
        "lightgbm",
        "catboost",
        "sklearn",
    ]

    for item in required_hiddenimports:
        assert item in content, f"Missing required hiddenimport '{item}' in sidecar.spec"
