"""
AIDSE Platform — Auth Module Tests
Section 23.5 (Testing Standards): Tests written BEFORE implementation.
Tests directly encode Phase 0 acceptance criteria (Section 18.2).

Coverage required:
- Every endpoint: success path + auth-failure path (Section 23.5)
- Refresh token rotation + reuse attack detection
- Token version invalidation (global logout)
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ─────────────────────────────────────────────
# POST /api/v1/auth/register
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    """A new user can register and receives access + refresh tokens."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "Password1"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    """Registering with an existing email returns 409 Conflict."""
    payload = {"name": "Alice", "email": "alice@example.com", "password": "Password1"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    body = resp.json()
    # FastAPI wraps our detail dict: {"detail": {"error": {"code": ..., "message": ...}}}
    assert "already registered" in body["detail"]["error"]["message"].lower()


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient) -> None:
    """Passwords without letters+digits are rejected at schema level."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": "Bob", "email": "bob@example.com", "password": "onlyletters"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient) -> None:
    """Passwords shorter than 8 chars are rejected."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": "Carol", "email": "carol@example.com", "password": "Abc1"},
    )
    assert resp.status_code == 422


# ─────────────────────────────────────────────
# POST /api/v1/auth/login
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, registered_user: dict) -> None:
    """A registered user can log in and receive tokens."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, registered_user: dict) -> None:
    """Wrong password returns 401 Unauthorized."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": "WrongPass1"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert "invalid" in body["detail"]["error"]["message"].lower()


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient) -> None:
    """Unknown email returns 401 (not 404 — avoid user enumeration)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Password1"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────
# POST /api/v1/auth/refresh
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_success(client: AsyncClient, logged_in_user: dict) -> None:
    """A valid refresh token returns a new access token."""
    client.cookies.set("refresh_token", logged_in_user["refresh_token"])
    
    resp = await client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body


@pytest.mark.asyncio
async def test_refresh_rotates_token(client: AsyncClient, logged_in_user: dict) -> None:
    """After refresh, the OLD refresh token must be invalidated."""
    client.cookies.set("refresh_token", logged_in_user["refresh_token"])
    
    # First refresh — succeeds
    resp1 = await client.post("/api/v1/auth/refresh", json={})
    assert resp1.status_code == 200
    new_access = resp1.json()["access_token"]
    assert new_access  # new access token issued
    
    # Reuse the SAME old refresh token again — must fail with 401 (reuse detection)
    resp2 = await client.post("/api/v1/auth/refresh", json={})
    assert resp2.status_code == 401, f"Expected 401, got {resp2.status_code}: {resp2.text}"


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient) -> None:
    """Garbage refresh token returns 401."""
    # Set an invalid token cookie
    client.cookies.set("refresh_token", "not.a.valid.jwt")
    
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


# ─────────────────────────────────────────────
# GET /api/v1/auth/me
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, logged_in_user: dict) -> None:
    """Authenticated user can fetch their profile."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {logged_in_user['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == logged_in_user["email"]
    assert "password_hash" not in data
    assert "refresh_token_hash" not in data


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient) -> None:
    """Without a token, /auth/me returns 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token(client: AsyncClient) -> None:
    """Invalid token returns 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limited(client: AsyncClient) -> None:
    """6th consecutive login attempt from same IP -> 429 (brute-force guard)."""
    from apps.api.core.rate_limit import limiter

    limiter.enabled = True
    try:
        payload = {"email": "ratelimit@example.com", "password": "WrongPass1"}
        codes = []
        for _ in range(6):
            resp = await client.post("/api/v1/auth/login", json=payload)
            codes.append(resp.status_code)
        assert codes[:5] == [401] * 5
        assert codes[5] == 429
    finally:
        limiter.enabled = False
