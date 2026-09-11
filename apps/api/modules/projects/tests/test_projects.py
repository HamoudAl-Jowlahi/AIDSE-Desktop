"""
AIDSE Platform — Projects Module Tests
Section 23.5 (Testing Standards): tests written BEFORE implementation.
Covers Phase 0 acceptance criteria: project CRUD + member invite.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ─────────────────────────────────────────────
# POST /api/v1/projects
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project_success(
    client: AsyncClient, auth_headers: dict
) -> None:
    """An authenticated user can create a project."""
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "My AI Project", "type": "evaluation"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My AI Project"
    assert data["project_type"] == "evaluation"
    assert "id" in data
    assert "owner_id" in data


@pytest.mark.asyncio
async def test_create_project_unauthenticated(client: AsyncClient) -> None:
    """Unauthenticated request returns 401."""
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Sneaky Project", "type": "general"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_project_creator_is_owner_member(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Project creator is automatically added as owner member."""
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Auto-Member Project", "type": "general"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    # Get members
    members_resp = await client.get(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
    )
    assert members_resp.status_code == 200
    # The project detail should show member_count ≥ 1
    assert members_resp.json()["member_count"] >= 1


# ─────────────────────────────────────────────
# GET /api/v1/projects
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, auth_headers: dict) -> None:
    """User sees only their own projects."""
    # Create 2 projects
    for name in ["Alpha", "Beta"]:
        await client.post(
            "/api/v1/projects",
            json={"name": name, "type": "general"},
            headers=auth_headers,
        )

    resp = await client.get("/api/v1/projects", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_projects_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 401


# ─────────────────────────────────────────────
# GET /api/v1/projects/{id}
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, auth_headers: dict) -> None:
    """Owner can get project details."""
    create_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Detail Project", "type": "automl"},
        headers=auth_headers,
    )
    project_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == project_id


@pytest.mark.asyncio
async def test_get_project_not_member(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
) -> None:
    """Non-member gets 404 (project existence should not be revealed)."""
    create_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Private Project", "type": "general"},
        headers=auth_headers,
    )
    project_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project_id}", headers=second_user_headers
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────
# POST /api/v1/projects/{id}/members
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invite_member_success(
    client: AsyncClient, auth_headers: dict, second_user: dict
) -> None:
    """Owner can invite a second user to a project."""
    project_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Collab Project", "type": "evaluation"},
        headers=auth_headers,
    )
    project_id = project_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": second_user["email"], "role": "viewer"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == "viewer"
    assert data["user_email"] == second_user["email"]


@pytest.mark.asyncio
async def test_invite_member_duplicate(
    client: AsyncClient, auth_headers: dict, second_user: dict
) -> None:
    """Inviting the same user twice returns 409."""
    project_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Dup Invite Project", "type": "general"},
        headers=auth_headers,
    )
    project_id = project_resp.json()["id"]

    invite_payload = {"email": second_user["email"], "role": "viewer"}
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json=invite_payload,
        headers=auth_headers,
    )
    resp = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json=invite_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_invite_member_insufficient_role(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict, second_user: dict
) -> None:
    """A viewer cannot invite other members (requires admin)."""
    project_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Role Test Project", "type": "general"},
        headers=auth_headers,
    )
    project_id = project_resp.json()["id"]

    # Invite second_user as viewer
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": second_user["email"], "role": "viewer"},
        headers=auth_headers,
    )

    # Viewer tries to invite someone else
    resp = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": "third@example.com", "role": "viewer"},
        headers=second_user_headers,
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────
# GET /api/v1/projects/{id}/audit-logs
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_logs_populated_on_create(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Creating a project generates an audit log entry."""
    project_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Audit Test Project", "type": "general"},
        headers=auth_headers,
    )
    project_id = project_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project_id}/audit-logs",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 1
    actions = [log["action"] for log in logs]
    assert "project_created" in actions


@pytest.mark.asyncio
async def test_delete_project_success(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Owner can delete a project."""
    project_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Project to Delete", "type": "general"},
        headers=auth_headers,
    )
    project_id = project_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 404
