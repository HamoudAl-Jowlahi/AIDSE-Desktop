"""
AIDSE Platform — Phase 3 Local Network Isolation Unit Tests
Section 3: Network Security & Internal Session Authorization
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from apps.api.core.network import find_free_loopback_port, validate_host_binding
from apps.api.main import create_app


def test_free_port_allocation():
    """Verify find_free_loopback_port returns an unprivileged valid TCP port on loopback."""
    port = find_free_loopback_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_host_binding_guard_rejects_public_interface():
    """Verify host binding guard raises ValueError when public 0.0.0.0 interface is configured."""
    with pytest.raises(ValueError, match="strictly forbidden in desktop mode"):
        validate_host_binding("0.0.0.0")


def test_host_binding_guard_allows_loopback():
    """Verify host binding guard allows 127.0.0.1 loopback interface."""
    validate_host_binding("127.0.0.1")


def test_internal_token_middleware_enforcement(monkeypatch):
    """Verify internal token middleware blocks unauthorized requests and permits authorized ones."""
    test_token = "secret_internal_session_token_12345"
    monkeypatch.setenv("AIDSE_INTERNAL_TOKEN", test_token)

    app = create_app()
    test_client = TestClient(app)

    # Request without token header -> 403 Forbidden
    resp_unauth = test_client.get("/health")
    assert resp_unauth.status_code == 403
    assert resp_unauth.json()["error"]["code"] == "FORBIDDEN"

    # Request with invalid token -> 403 Forbidden
    resp_invalid = test_client.get(
        "/health",
        headers={"X-AIDSE-Internal-Token": "wrong_token"}
    )
    assert resp_invalid.status_code == 403

    # Request with valid internal token -> 200 OK
    resp_valid = test_client.get(
        "/health",
        headers={"X-AIDSE-Internal-Token": test_token}
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["status"] == "ok"
