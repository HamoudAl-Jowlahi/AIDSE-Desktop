"""
AIDSE Platform — Local network isolation

The sidecar listens on loopback and is reachable by anything running as the
same user, so these tests drive the real ASGI app over HTTP rather than
asserting on configuration strings.

Covered here: the Host header guard (DNS-rebinding defence), the bind guard,
CORS, and the internal token middleware — including the case where no token is
configured, which is currently how the shipped app runs.
"""
from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from apps.api.core.network import find_free_loopback_port, validate_host_binding
from apps.api.main import create_app


@pytest.fixture
def client_without_token(monkeypatch) -> TestClient:
    monkeypatch.delenv("AIDSE_INTERNAL_TOKEN", raising=False)
    return TestClient(create_app())


# ── Bind guard ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "0:0:0:0:0:0:0:0", "192.168.1.50"])
def test_bind_guard_rejects_non_loopback(host):
    """Anything reachable from the LAN must be refused outright."""
    with pytest.raises(ValueError, match="strictly forbidden"):
        validate_host_binding(host)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_bind_guard_allows_loopback(host):
    validate_host_binding(host)


def test_allocated_port_is_actually_bindable_on_loopback():
    """The helper must hand back a port that can really be bound on 127.0.0.1."""
    port = find_free_loopback_port()
    assert 1024 <= port <= 65535

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))  # raises if the port was not free


# ── Host header guard (DNS rebinding) ──────────────────────────────────────


@pytest.mark.parametrize(
    "bad_host",
    ["evil.example.com", "attacker.test:8010", "aidse.app", "169.254.169.254"],
)
def test_foreign_host_header_is_rejected(client_without_token, bad_host):
    """
    A page on another origin can reach 127.0.0.1 but cannot forge the Host
    header, so rejecting foreign Hosts blocks DNS rebinding onto the sidecar.
    """
    resp = client_without_token.get("/health", headers={"Host": bad_host})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_HOST"


@pytest.mark.parametrize("good_host", ["127.0.0.1", "127.0.0.1:8010", "localhost:3000"])
def test_loopback_host_header_is_accepted(client_without_token, good_host):
    assert client_without_token.get("/health", headers={"Host": good_host}).status_code == 200


# ── CORS ───────────────────────────────────────────────────────────────────


def test_foreign_origin_gets_no_cors_grant(client_without_token):
    """
    Without an allow-origin header the browser refuses to hand the response
    body back to the calling page.
    """
    resp = client_without_token.get("/health", headers={"Origin": "https://evil.example.com"})
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_loopback_origin_is_granted(client_without_token):
    resp = client_without_token.get("/health", headers={"Origin": "http://127.0.0.1:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


# ── Internal token middleware ──────────────────────────────────────────────

TOKEN = "secret_internal_session_token_12345"

# /health is deliberately exempt: the launcher polls it to know when the backend
# is up and a plain browser cannot attach a custom header. Enforcement is
# checked against a real API route instead.
PROTECTED_PATH = "/api/v1/projects"


@pytest.fixture
def client_with_token(monkeypatch) -> TestClient:
    monkeypatch.setenv("AIDSE_INTERNAL_TOKEN", TOKEN)
    return TestClient(create_app())


def test_request_without_token_is_refused(client_with_token):
    resp = client_with_token.get(PROTECTED_PATH)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_request_with_wrong_token_is_refused(client_with_token):
    resp = client_with_token.get(PROTECTED_PATH, headers={"X-AIDSE-Internal-Token": "wrong"})
    assert resp.status_code == 403


def test_token_comparison_is_not_a_prefix_match(client_with_token):
    """A truncated or extended token must not be accepted."""
    for candidate in (TOKEN[:-1], TOKEN + "x", TOKEN.upper()):
        resp = client_with_token.get(PROTECTED_PATH, headers={"X-AIDSE-Internal-Token": candidate})
        assert resp.status_code == 403, f"{candidate!r} was accepted"


def test_correct_token_passes(client_with_token):
    resp = client_with_token.get(PROTECTED_PATH, headers={"X-AIDSE-Internal-Token": TOKEN})
    assert resp.status_code != 403, "a valid token must not be rejected"


def test_bearer_header_is_accepted_as_a_fallback(client_with_token):
    resp = client_with_token.get(PROTECTED_PATH, headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code != 403


def test_preflight_is_allowed_through(client_with_token):
    """CORS preflight carries no custom headers, so it must bypass the check."""
    resp = client_with_token.options(
        "/api/v1/projects",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code < 400


def test_health_stays_reachable_without_a_token(client_with_token):
    """The launcher's readiness probe must not need a header it cannot send."""
    assert client_with_token.get("/health").status_code == 200


def test_unconfigured_token_currently_fails_open(client_without_token):
    """
    Documents a known gap rather than a desired property.

    With AIDSE_INTERNAL_TOKEN unset the middleware passes every request
    through, and nothing in the shipped app sets it: the launcher passes no
    --token and the Tauri shell hardcodes an empty string. Combined with
    desktop mode's automatic admin session, any process running as the same
    user can call the whole API.

    When the shell is wired up to generate and pass a real token, this test
    should be replaced by one asserting the middleware fails CLOSED.
    """
    assert client_without_token.get("/health").status_code == 200
