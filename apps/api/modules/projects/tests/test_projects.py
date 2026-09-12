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


# ── Regression: deleting a project must take its children with it ──────────


@pytest.mark.asyncio
async def test_delete_project_cascades_to_experiments(client: AsyncClient, auth_headers: dict, db):
    """
    Experiment reached Project through a plain backref, which carries no
    cascade, so SQLAlchemy tried to NULL experiments.project_id — a NOT NULL
    column — and deleting any project that had ever been trained on failed
    with a 500. conversations and provider_credentials had the same shape.

    Scope, stated honestly: this asserts the OUTCOME (project and children are
    gone, endpoint returns 204). It does not reproduce the original failure.
    That fault only appears when the deleting session already holds the
    experiments collection, and it could not be reproduced against the
    in-memory database this suite uses — configured exactly as it was when it
    broke, this still passes. The fix was verified by hand against a real
    file-backed database, where the delete failed before and succeeds after.
    Treat a regression here as possible even if this test stays green.
    """
    import uuid as _uuid

    from sqlalchemy import select

    from apps.api.modules.automl.models import Experiment, ModelTrial
    from apps.api.modules.datasets.models import Dataset
    from apps.api.modules.projects.models import Project

    created = await client.post("/api/v1/projects",
                                json={"name": "Cascade Check", "type": "ml"},
                                headers=auth_headers)
    assert created.status_code == 201
    project_id = _uuid.UUID(created.json()["id"])

    dataset = Dataset(project_id=project_id, name="ds", format="csv")
    db.add(dataset)
    await db.flush()

    experiment = Experiment(
        project_id=project_id,
        dataset_id=dataset.id,
        target_column="y",
        problem_type="classification",
        primary_metric="f1_macro",
        status="completed",
    )
    db.add(experiment)
    await db.flush()

    db.add(ModelTrial(
        experiment_id=experiment.id,
        algorithm_name="random_forest",
        hyperparameters={},
        metrics={"f1_macro": 0.8},
        primary_metric_score=0.8,
        status="completed",
    ))
    await db.commit()

    resp = await client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 204, resp.text

    db.expire_all()
    assert (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none() is None
    assert (await db.execute(
        select(Experiment).where(Experiment.project_id == project_id)
    )).scalar_one_or_none() is None, "experiment outlived its project"
    assert (await db.execute(
        select(ModelTrial).where(ModelTrial.experiment_id == experiment.id)
    )).scalar_one_or_none() is None, "trial outlived its experiment"
