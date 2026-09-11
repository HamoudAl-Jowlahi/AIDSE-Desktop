"""
AIDSE Platform — Phase 5 Headless Migrations & First-Run Onboarding Unit Tests
Section 5: Database Migrations & Local Onboarding Sequence
"""
from __future__ import annotations

from pathlib import Path
from apps.api.db.migrations_runner import run_migrations_headless


def test_run_migrations_headless():
    """Verify headless Alembic migrations function executes without raising exceptions."""
    # Should complete silently without requiring CLI input
    run_migrations_headless()


def test_login_screens_replaced_with_onboarding():
    """Verify login and register pages have been replaced with local-first onboarding redirects."""
    repo_root = Path(__file__).resolve().parents[3]
    login_page = repo_root / "apps" / "web" / "app" / "(auth)" / "login" / "page.tsx"
    register_page = repo_root / "apps" / "web" / "app" / "(auth)" / "register" / "page.tsx"

    assert login_page.exists()
    assert register_page.exists()

    login_content = login_page.read_text(encoding="utf-8")
    register_content = register_page.read_text(encoding="utf-8")

    # Confirm no traditional username/password form inputs exist on auth routes
    assert '<input id="password"' not in login_content
    assert '<input id="email"' not in login_content
    assert 'router.replace("/onboarding")' in login_content or "router.replace" in login_content

    assert '<input id="password"' not in register_content
    assert '<input id="email"' not in register_content


def test_onboarding_wizard_components():
    """Verify OnboardingWizard component exists and contains all 6 required onboarding steps."""
    repo_root = Path(__file__).resolve().parents[3]
    wizard_file = repo_root / "apps" / "web" / "components" / "onboarding" / "OnboardingWizard.tsx"

    assert wizard_file.exists(), f"OnboardingWizard component missing at {wizard_file}"
    content = wizard_file.read_text(encoding="utf-8")

    # Verify required 6 steps are implemented
    assert "Analyze and evaluate your models, fully offline" in content  # Step 1: Welcome
    assert "100% On-Device Processing" in content                      # Step 2: Privacy Summary
    assert "Optional App Lock" in content                             # Step 3: Optional Lock
    assert "Local Workspace Location" in content                      # Step 4: Workspace Path
    assert "Optional Cloud Features" in content                       # Step 5: Optional Cloud
    assert "Finish Setup & Open Dashboard" in content                 # Step 6: Direct to Dashboard
