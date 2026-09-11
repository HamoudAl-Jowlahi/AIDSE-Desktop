"""
AIDSE Platform — Reports + Security Isolation Tests (Phases 15 & 17)
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.api.modules.datasets.tests.test_ingestion import (
    create_dataset,
    create_project,
    csv_bytes,
    sample_frame,
)


async def _seed_full_project(client: AsyncClient, auth_headers: dict) -> str:
    """Upload a dataset, train nothing (fast), run one evaluation."""
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])
    up = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/upload",
        files={"file": ("data.csv", csv_bytes(sample_frame()), "text/csv")},
        headers=auth_headers,
    )
    assert up.status_code == 201

    gid = (await client.post(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets",
        json={"name": "G"}, headers=auth_headers)).json()["id"]
    bulk = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}/cases/bulk",
        json={"cases": [{"input_data": "q", "expected_output": "a"}]},
        headers=auth_headers)
    case_id = bulk.json()[0]["id"]
    await client.post(
        f"/api/v1/projects/{project['id']}/evaluations/runs",
        json={"golden_dataset_id": gid, "provider": "t", "scoring_strategy": "exact",
              "actual_outputs": {case_id: "a"}},
        headers=auth_headers)
    return project["id"]


@pytest.mark.asyncio
async def test_report_contains_all_sections(client: AsyncClient, auth_headers: dict):
    pid = await _seed_full_project(client, auth_headers)

    resp = await client.get(f"/api/v1/projects/{pid}/report", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Summary counts everything seeded
    s = body["summary"]
    assert s["datasets"] == 1
    assert s["golden_datasets"] == 1
    assert s["evaluation_runs"] == 1

    # Dataset section carries profile + quality totals
    ds = body["datasets"][0]
    assert ds["num_rows"] == 100
    assert set(ds["quality"].keys()) == {"critical", "warning", "info"}
    assert body["summary"]["data_quality_totals"]["warning"] >= ds["quality"]["warning"]

    # Evaluation section reflects the executed run
    ev = body["ai_evaluation"][0]
    assert ev["total_runs"] == 1
    assert ev["latest_run"]["status"] == "completed"
    assert ev["latest_run"]["pass_rate"] == 1.0

    # ML section present but empty (no training in this test)
    assert body["ml_results"] == []


@pytest.mark.asyncio
async def test_report_empty_project_is_clean(client: AsyncClient, auth_headers: dict):
    pid = (await create_project(client, auth_headers))["id"]
    resp = await client.get(f"/api/v1/projects/{pid}/report", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["datasets"] == 0
    assert body["datasets"] == [] and body["ml_results"] == [] and body["ai_evaluation"] == []


@pytest.mark.asyncio
async def test_cross_tenant_access_denied(client: AsyncClient, auth_headers: dict, second_user_headers: dict):
    """Phase 17: another user's project must be invisible — 404, never data."""
    pid = await _seed_full_project(client, auth_headers)

    for path in (
        f"/api/v1/projects/{pid}",
        f"/api/v1/projects/{pid}/report",
        f"/api/v1/projects/{pid}/evaluations/runs",
    ):
        r = await client.get(path, headers=second_user_headers)
        assert r.status_code in (403, 404), f"{path} leaked status {r.status_code}"


@pytest.mark.asyncio
async def test_evaluation_run_creation_is_audited(client: AsyncClient, auth_headers: dict):
    pid = await _seed_full_project(client, auth_headers)

    logs = await client.get(f"/api/v1/projects/{pid}/audit-logs", headers=auth_headers)
    assert logs.status_code == 200
    actions = [entry["action"] for entry in logs.json()]
    assert "evaluation.run.executed" in actions
