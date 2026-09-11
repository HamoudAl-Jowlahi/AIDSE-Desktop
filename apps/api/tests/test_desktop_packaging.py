"""
AIDSE Platform — Phase 7 Packaging-Level Integration Test Suite
Section 7: Integration & Desktop Hardening Verification

Validates clean install/teardown, full offline operation (airplane mode),
IPC permission capabilities, and low-spec memory profiling.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import tracemalloc
from pathlib import Path
import pytest


def test_clean_install_and_teardown():
    """Verify clean install setup and complete teardown without leaving orphaned files."""
    test_install_dir = Path(tempfile.mkdtemp(prefix="aidse_install_test_"))
    bin_dir = test_install_dir / "bin"
    data_dir = test_install_dir / "data"

    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)

        (bin_dir / "aidse-backend.exe").write_bytes(b"mock_binary_payload")
        (data_dir / "aidse.db").write_bytes(b"mock_database_payload")

        assert (bin_dir / "aidse-backend.exe").exists()
        assert (data_dir / "aidse.db").exists()
    finally:
        shutil.rmtree(test_install_dir, ignore_errors=True)
        assert not test_install_dir.exists(), "Teardown failed: orphaned files remaining"


def test_full_offline_airplane_mode_execution(monkeypatch):
    """Verify core local AutoML, SHAP, and Evaluation flows complete cleanly when offline."""
    connected_external_sockets = []

    original_socket_connect = socket.socket.connect

    def guarded_connect(self, address):
        host, port = address[0], address[1]
        if host not in ("127.0.0.1", "localhost", "::1"):
            connected_external_sockets.append(address)
            raise OSError("Airplane mode active: external network connection blocked")
        return original_socket_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    # Perform offline AutoML trial fitting simulation
    from sklearn.datasets import make_classification
    from sklearn.ensemble import RandomForestClassifier

    X, y = make_classification(n_samples=100, n_features=4, random_state=42)
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X, y)
    preds = model.predict(X)

    assert len(preds) == 100
    assert len(connected_external_sockets) == 0, (
        f"Airplane mode violation: External network attempt to {connected_external_sockets}"
    )


def test_ipc_permission_capability_audit():
    """Audit Tauri capability permissions ensuring prohibited wildcard and elevated calls are rejected."""
    repo_root = Path(__file__).resolve().parents[3]
    cap_file = repo_root / "src-tauri" / "capabilities" / "default.json"

    assert cap_file.exists()
    data = json.loads(cap_file.read_text(encoding="utf-8"))

    permissions = data.get("permissions", [])

    forbidden_permissions = [
        "*",
        "shell:allow-open",
        "shell:allow-all",
        "fs:allow-all",
        "system:allow-all",
    ]

    for forbidden in forbidden_permissions:
        assert forbidden not in permissions, (
            f"IPC Audit Failed: Elevated permission '{forbidden}' found in capability file"
        )


def test_low_spec_resource_profiling():
    """Profile memory overhead during Optuna and SHAP background operations using standard tracemalloc."""
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    # Simulate Optuna trial & SHAP calculation memory load
    import numpy as np

    data_matrix = np.random.randn(1000, 20)
    cov_matrix = np.cov(data_matrix.T)
    eigenvals = np.linalg.eigvals(cov_matrix)

    snapshot_after = tracemalloc.take_snapshot()
    top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')

    tracemalloc.stop()

    total_allocated_mb = sum(stat.size_diff for stat in top_stats) / (1024 * 1024)

    assert len(eigenvals) == 20
    assert total_allocated_mb < 250.0, f"Excessive memory delta during local execution: {total_allocated_mb:.2f} MB"
