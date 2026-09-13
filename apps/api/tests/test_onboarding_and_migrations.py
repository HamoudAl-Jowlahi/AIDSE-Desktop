"""
AIDSE Platform — Headless migrations and first-run onboarding

The onboarding assertions here are deliberately narrow: they check that the
wizard makes no security promise the product does not keep. An earlier version
asserted that a step called "Optional App Lock" was present, which pinned in
place a screen that collected a 4-digit PIN, wrote it to localStorage in
cleartext, and never read it back — the lock was never enforced anywhere.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.db.migrations_runner import run_migrations_headless

REPO_ROOT = Path(__file__).resolve().parents[3]
WIZARD = REPO_ROOT / "apps" / "web" / "components" / "onboarding" / "OnboardingWizard.tsx"


def _wizard_source() -> str:
    assert WIZARD.exists(), f"OnboardingWizard component missing at {WIZARD}"
    return WIZARD.read_text(encoding="utf-8")


# ── Migrations ─────────────────────────────────────────────────────────────


def test_run_migrations_headless_is_callable_without_a_terminal():
    """Startup runs this with no CLI; it must not raise or prompt."""
    run_migrations_headless()


def test_migration_runner_resolves_the_repo_root():
    """
    It computed the root one directory too low, so it never found alembic.ini
    and returned silently on every launch.
    """
    from apps.api.db import migrations_runner

    root = migrations_runner._repo_root()
    assert (root / "alembic.ini").is_file(), (
        f"_repo_root() returned {root}, which holds no alembic.ini"
    )
    assert (root / "apps" / "api" / "db" / "migrations" / "versions").is_dir()


# ── Auth routes are inert in a local-first build ────────────────────────────


def test_login_and_register_collect_no_credentials():
    login = REPO_ROOT / "apps" / "web" / "app" / "(auth)" / "login" / "page.tsx"
    register = REPO_ROOT / "apps" / "web" / "app" / "(auth)" / "register" / "page.tsx"

    for page in (login, register):
        assert page.exists()
        content = page.read_text(encoding="utf-8")
        assert '<input id="password"' not in content
        assert '<input id="email"' not in content

    assert "router.replace" in login.read_text(encoding="utf-8")


# ── Onboarding ─────────────────────────────────────────────────────────────


def test_onboarding_covers_its_steps():
    content = _wizard_source()

    for marker in (
        "Analyze and evaluate your models, fully offline",  # welcome
        "100% On-Device Processing",                        # privacy
        "Local Workspace Location",                         # workspace
        "Optional Cloud Features",                          # opt-in egress
        "Finish Setup & Open Dashboard",                    # finish
    ):
        assert marker in content, f"onboarding step missing: {marker}"


def test_onboarding_never_stores_a_pin():
    """
    Writing a user-chosen PIN to localStorage in cleartext is worse than having
    no lock: people reuse PINs, and nothing here ever enforced it.
    """
    content = _wizard_source()

    assert 'setItem("aidse_pin_code"' not in content, (
        "the wizard writes a PIN to localStorage in cleartext"
    )
    assert 'maxLength={4}' not in content, "the wizard still collects a PIN"
    assert "Optional App Lock" not in content, (
        "the app-lock screen is back; it promises protection that is not implemented"
    )


def test_onboarding_clears_any_pin_left_by_an_older_build():
    """Upgrading users must not keep a cleartext PIN on disk."""
    content = _wizard_source()
    assert 'removeItem("aidse_pin_code")' in content


def test_onboarding_claims_no_encryption_the_product_lacks():
    """
    The privacy step told every user their datasets were protected by AES-256
    SQLCipher. The database is a plain SQLite file.
    """
    content = _wizard_source()
    for phrase in ("SQLCipher", "AES-256"):
        assert phrase not in content, (
            f"onboarding claims {phrase!r}; whole-database encryption is not implemented"
        )

    # The workspace step also described the files themselves as encrypted.
    # Provider credentials are encrypted; datasets and project files are not.
    for phrase in ("encrypted local project files", "encrypted datasets"):
        assert phrase not in content, (
            f"onboarding describes stored data as {phrase!r}; only provider "
            "credentials are encrypted"
        )


@pytest.mark.parametrize(
    "path",
    [
        Path("apps") / "web" / "components" / "onboarding" / "OnboardingWizard.tsx",
        Path("landing-page") / "index.html",
        Path("README.md"),
        Path("docs") / "local_privacy_guide.md",
    ],
)
def test_no_user_facing_surface_claims_sqlcipher(path):
    """
    The claim appeared in the app, the marketing page (both languages) and the
    docs. Two files are excluded because they name SQLCipher only to say it is
    absent and explain what replaced it: docs/threat_model.md and
    AIDSE_COMPLETE_PROJECT_DOCS.md. Recording that a false claim was made is
    the opposite of making it.

    README_DESKTOP.md used to be on this list. It was a second, partly stale
    readme — it told the reader to run start-backend.bat and
    start-frontend.bat, neither of which exists — and README.md took its place.
    """
    target = REPO_ROOT / path
    if not target.is_file():
        pytest.skip(f"{path} not present")

    content = target.read_text(encoding="utf-8")
    assert "SQLCipher" not in content, f"{path} claims SQLCipher encryption"
