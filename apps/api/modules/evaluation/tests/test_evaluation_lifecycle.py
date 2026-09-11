"""
AIDSE Platform — Golden Dataset Management + AI Evaluation + Regression Tests
(Phases 12-14)

Covers:
- Scoring strategies: exact / regex / semantic / llm_judge fallback
- Run execution end-to-end (results, aggregates, failed cases)
- Golden dataset CRUD completion + bulk import
- Regression report verdicts (PASS/WARN/FAIL) + flaky detection
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from apps.api.modules.evaluation.scoring import score_case, score_semantic

from apps.api.modules.datasets.tests.test_ingestion import create_project


# ──────────────────────────────────────────────────────────────────────────────
# Phase 13 — scoring strategies
# ──────────────────────────────────────────────────────────────────────────────

def test_exact_match_pass_and_fail():
    assert score_case("exact", "Paris", "  paris \n")["passed"] is True   # case-insensitive default
    r = score_case("exact", "Paris", "London")
    assert r["score"] == 0.0 and r["passed"] is False
    # case-sensitive mode distinguishes
    r = score_case("exact", "Paris", "paris", {"case_insensitive": False})
    assert r["passed"] is False


def test_regex_strategy_uses_expected_as_pattern():
    assert score_case("regex", r"^\d{3}-\d{4}$", "555-1234")["passed"] is True
    r = score_case("regex", r"^\d{3}-\d{4}$", "call 555-1234 now")
    assert r["passed"] is False
    # full_match anchors
    assert score_case("regex", r"\d{3}-\d{4}", "call 555-1234", {"full_match": False})["passed"] is True


def test_invalid_regex_scores_zero_with_error_not_crash():
    r = score_case("regex", "([unclosed", "anything")
    assert r["score"] == 0.0
    assert "Invalid pattern" in r["detail"]["error"]


def test_semantic_similarity_grading():
    high = score_case("semantic", "The capital of France is Paris.", "Paris is the capital of France.")
    assert high["score"] > 0.8 and high["passed"]
    low = score_semantic("The capital of France is Paris.", "I like turtles.")
    assert low["score"] < 0.3
    custom = score_case("semantic", "hello world", "hello there", {"threshold": 0.1})
    assert custom["pass_threshold"] == 0.1


def test_llm_judge_falls_back_offline_and_says_so(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    from apps.api.core.config import get_settings
    get_settings.cache_clear()
    r = score_case("llm_judge", "The sky is blue.", "The sky is blue.")
    assert r["detail"]["method"].startswith("llm_judge_fallback")
    assert "provider" in r["detail"]["note"].lower() or "configured" in r["detail"]["note"].lower()
    get_settings.cache_clear()


def test_unknown_strategy_rejected():
    with pytest.raises(ValueError, match="Supported"):
        score_case("vibes", "a", "b")


# ──────────────────────────────────────────────────────────────────────────────
# End-to-end helpers
# ──────────────────────────────────────────────────────────────────────────────

async def make_golden(client: AsyncClient, auth_headers: dict, project_id: str, cases: list[dict]) -> str:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets/golden-datasets",
        json={"name": f"GOLD-{uuid.uuid4().hex[:6]}"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    gid = resp.json()["id"]
    bulk = await client.post(
        f"/api/v1/projects/{project_id}/datasets/golden-datasets/{gid}/cases/bulk",
        json={"cases": cases},
        headers=auth_headers,
    )
    assert bulk.status_code == 201, bulk.text
    return gid


async def run_eval(client: AsyncClient, auth_headers: dict, project_id: str, gid: str,
                   strategy: str, outputs: dict[str, str], params: dict | None = None):
    return await client.post(
        f"/api/v1/projects/{project_id}/evaluations/runs",
        json={
            "golden_dataset_id": gid,
            "provider": "test-suite",
            "scoring_strategy": strategy,
            "scoring_params": params or {},
            "actual_outputs": outputs,
        },
        headers=auth_headers,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Phase 12 — golden CRUD
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_import_and_edit_delete_case(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    gid = await make_golden(client, auth_headers, project["id"], [
        {"input_data": "q1", "expected_output": "a1", "category_tag": "math"},
        {"input_data": "q2", "expected_output": "a2", "category_tag": "critical"},
    ])

    listing = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets", headers=auth_headers)
    cases = listing.json()[0]["cases"]
    assert len(cases) == 2
    case_id = cases[0]["id"]

    edit = await client.patch(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}/cases/{case_id}",
        json={"expected_output": "a1-updated"},
        headers=auth_headers,
    )
    assert edit.status_code == 200 and edit.json()["expected_output"] == "a1-updated"

    deleted = await client.delete(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}/cases/{case_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204

    renamed = await client.patch(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}",
        json={"name": "Renamed", "version": 2},
        headers=auth_headers,
    )
    assert renamed.json()["name"] == "Renamed" and renamed.json()["version"] == 2

    gone = await client.delete(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}",
        headers=auth_headers,
    )
    assert gone.status_code == 204


@pytest.mark.asyncio
async def test_bulk_empty_rejected(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    gid = await make_golden(client, auth_headers, project["id"], [
        {"input_data": "q", "expected_output": "a"},
    ])
    bad = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}/cases/bulk",
        json={"cases": []}, headers=auth_headers)
    assert bad.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# Phase 13 — run execution
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_executes_exact_strategy_end_to_end(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    gid = await make_golden(client, auth_headers, project["id"], [
        {"input_data": "capital of France?", "expected_output": "Paris"},
        {"input_data": "capital of Japan?", "expected_output": "Tokyo", "category_tag": "critical"},
    ])

    listing = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets", headers=auth_headers)
    cases = {c["input_data"]: c["id"] for c in listing.json()[0]["cases"]}

    resp = await run_eval(client, auth_headers, project["id"], gid, "exact", {
        cases["capital of France?"]: "Paris",
        cases["capital of Japan?"]: "Osaka",   # wrong on purpose → critical fail
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["scoring_strategy"] == "exact"
    agg = body["aggregate_results"]
    assert agg["total_cases"] == 2 and agg["passed_cases"] == 1 and agg["failed_cases"] == 1
    assert len(agg["failure_details"]) == 1
    assert agg["pass_rate"] == 0.5
    assert agg["per_tag"]["critical"]["passed"] == 0
    statuses = {r["status"] for r in body["results"]}
    assert statuses == {"pass", "fail"}


@pytest.mark.asyncio
async def test_run_without_outputs_fails_honestly(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    gid = await make_golden(client, auth_headers, project["id"], [
        {"input_data": "q", "expected_output": "a"},
    ])
    resp = await run_eval(client, auth_headers, project["id"], gid, "exact", {})
    body = resp.json()
    assert body["status"] == "failed"
    assert "actual output" in body["aggregate_results"]["error"].lower()


@pytest.mark.asyncio
async def test_unknown_strategy_rejected_at_api(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    gid = await make_golden(client, auth_headers, project["id"], [
        {"input_data": "q", "expected_output": "a"},
    ])
    resp = await run_eval(client, auth_headers, project["id"], gid, "vibes", {})
    assert resp.status_code == 400
    assert "Supported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_runs_history_listed(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    gid = await make_golden(client, auth_headers, project["id"], [
        {"input_data": "q", "expected_output": "a"},
    ])
    listing = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets", headers=auth_headers)
    case_id = listing.json()[0]["cases"][0]["id"]

    await run_eval(client, auth_headers, project["id"], gid, "exact", {case_id: "a"})
    await run_eval(client, auth_headers, project["id"], gid, "exact", {case_id: "WRONG"})

    history = await client.get(
        f"/api/v1/projects/{project['id']}/evaluations/runs",
        params={"golden_dataset_id": gid},
        headers=auth_headers,
    )
    assert history.status_code == 200
    runs = history.json()
    assert len(runs) >= 2
    pass_rates = sorted(r["aggregate_results"]["pass_rate"] for r in runs)
    assert pass_rates == [0.0, 1.0]


# ──────────────────────────────────────────────────────────────────────────────
# Phase 14 — baseline comparison + verdicts + flaky detection
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_regression_flow_with_verdicts(client: AsyncClient, auth_headers: dict):
    """Baseline all-pass → next run regresses critical → FAIL; then fix → PASS."""
    project = await create_project(client, auth_headers)
    gid = await make_golden(client, auth_headers, project["id"], [
        {"input_data": "q1", "expected_output": "good", "category_tag": "critical"},
        {"input_data": "q2", "expected_output": "also good", "category_tag": "minor"},
    ])
    listing = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets", headers=auth_headers)
    cases = {c["input_data"]: c["id"] for c in listing.json()[0]["cases"]}

    # Baseline: everything passes → mark as baseline
    base_resp = await run_eval(client, auth_headers, project["id"], gid, "exact", {
        cases["q1"]: "good", cases["q2"]: "also good",
    })
    baseline_id = base_resp.json()["id"]
    await client.post(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}/baseline",
        json={"run_id": baseline_id}, headers=auth_headers)

    # Regress q1 (critical): expect FAIL verdict
    bad = await run_eval(client, auth_headers, project["id"], gid, "exact", {
        cases["q1"]: "broken", cases["q2"]: "also good",
    })
    bad_id = bad.json()["id"]
    report = await client.post(
        f"/api/v1/projects/{project['id']}/evaluations/runs/{bad_id}/regression-report",
        headers=auth_headers)
    assert report.status_code == 201

    verdict = await client.get(
        f"/api/v1/projects/{project['id']}/evaluations/runs/{bad_id}/regression-report",
        headers=auth_headers)
    vbody = verdict.json()
    assert vbody["verdict"] == "FAIL"
    assert vbody["critical_regressions"] == 1
    assert any(c["status_transition"] == "Regressed" for c in vbody["cases"])
    gate = await client.get(
        f"/api/v1/projects/{project['id']}/evaluations/runs/{bad_id}/gate",
        headers=auth_headers)
    assert gate.status_code == 406  # CI gate blocks the ship

    # Fix both, AND point the baseline at the broken run so the fixed run
    # demonstrates "Newly Passing" transitions.
    fixed = await run_eval(client, auth_headers, project["id"], gid, "exact", {
        cases["q1"]: "good", cases["q2"]: "also good",
    })
    fixed_id = fixed.json()["id"]

    await client.post(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}/baseline",
        json={"run_id": bad_id}, headers=auth_headers)

    v2 = (await client.get(
        f"/api/v1/projects/{project['id']}/evaluations/runs/{fixed_id}/regression-report",
        headers=auth_headers)).json()
    assert v2["verdict"] == "PASS"
    assert v2["newly_passing_cases"] == 1


@pytest.mark.asyncio
async def test_flaky_case_detected_from_history(client: AsyncClient, auth_headers: dict):
    """A case alternating pass/fail/pass across runs gets flagged flaky."""
    project = await create_project(client, auth_headers)
    gid = await make_golden(client, auth_headers, project["id"], [
        {"input_data": "dicey", "expected_output": "stable answer"},
        {"input_data": "solid", "expected_output": "always right", "category_tag": "x"},
    ])
    listing = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets", headers=auth_headers)
    cases = {c["input_data"]: c["id"] for c in listing.json()[0]["cases"]}

    seq = [
        {cases["dicey"]: "stable answer", cases["solid"]: "always right"},   # pass
        {cases["dicey"]: "wrong",         cases["solid"]: "always right"},   # dicey fails
        {cases["dicey"]: "stable answer", cases["solid"]: "always right"},   # dicey passes again
    ]
    run_ids = []
    for outputs in seq:
        r = await run_eval(client, auth_headers, project["id"], gid, "exact", outputs)
        run_ids.append(r.json()["id"])

    await client.post(
        f"/api/v1/projects/{project['id']}/datasets/golden-datasets/{gid}/baseline",
        json={"run_id": run_ids[0]}, headers=auth_headers)

    last = await client.post(
        f"/api/v1/projects/{project['id']}/evaluations/runs/{run_ids[2]}/regression-report",
        headers=auth_headers)
    assert last.status_code == 201

    verdict = (await client.get(
        f"/api/v1/projects/{project['id']}/evaluations/runs/{run_ids[2]}/regression-report",
        headers=auth_headers)).json()

    flaky_ids = {str(f["golden_case_id"]) for f in verdict["flaky_cases"]}
    assert cases["dicey"] in flaky_ids
    assert cases["solid"] not in flaky_ids
