"""
AIDSE Platform — Dependency pinning

The app ships as a PyInstaller bundle compiled from whatever the
requirements resolve to at build time. A floating range means the installer
users download was built against versions nobody ran the suite on, and the
difference only shows up on their machine.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME = REPO_ROOT / "requirements.txt"
DEV = REPO_ROOT / "requirements-dev.txt"


def _requirements(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


@pytest.mark.parametrize("path", [RUNTIME, DEV], ids=["runtime", "dev"])
def test_every_dependency_is_pinned_exactly(path: Path):
    loose = [r for r in _requirements(path) if "==" not in r]
    assert not loose, (
        f"{path.name} leaves these unpinned: {loose}. A range here means the "
        "shipped bundle can be built from untested versions."
    )


def test_dev_tools_do_not_leak_into_the_runtime_file():
    """
    The release workflow installs requirements.txt alone. Anything the app
    needs at runtime has to be there, and nothing else should be.
    """
    names = {re.split(r"[=\[]", r, maxsplit=1)[0] for r in _requirements(RUNTIME)}
    dev_only = {"pytest", "pytest-asyncio", "pytest-cov", "ruff", "black", "pyinstaller"}
    leaked = names & dev_only
    assert not leaked, f"development tools in the runtime requirements: {sorted(leaked)}"


def test_the_packages_removed_as_unused_have_not_returned():
    """
    asyncpg, minio, celery and redis came from the multi-tenant server this
    app was forked from. Nothing imports them; celery's only importer was a
    scaffold package needing a Redis broker no desktop install has.
    """
    both = set()
    for path in (RUNTIME, DEV):
        both |= {re.split(r"[=\[]", r, maxsplit=1)[0] for r in _requirements(path)}

    server_era = {"asyncpg", "minio", "celery", "redis", "kombu", "passlib"}
    returned = both & server_era
    assert not returned, (
        f"server-era dependencies are back in the requirements: {sorted(returned)}"
    )


def test_the_workflow_installs_the_pinned_runtime_file():
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert "pip install -r requirements.txt" in workflow, (
        "the release build does not install the pinned runtime requirements"
    )
    assert re.search(r"pip install pyinstaller==\d", workflow), (
        "PyInstaller is installed unpinned in the release build, so the bundler "
        "itself can change underneath a release"
    )
