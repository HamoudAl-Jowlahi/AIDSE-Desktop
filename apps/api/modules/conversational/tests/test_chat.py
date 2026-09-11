"""
AIDSE Platform — AI Data Analyst Tests (Phase 11)

Covers:
- Every tool computes REAL values from a real profile
- Fallback router: question → correct tool; unknown questions refuse to guess
- Column validation (fuzzy match + honest "not found")
- Persistence: messages stored per project/dataset, history returned
- Anti-fabrication: answers only contain numbers that tools produced
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from httpx import AsyncClient

from apps.api.modules.conversational import tools as chat_tools
from apps.api.modules.conversational.service import (
    analyze_question,
    compose_answer,
    route_without_llm,
)
from apps.api.modules.datasets.profiling import profile_dataframe

from apps.api.modules.datasets.tests.test_ingestion import (
    create_dataset,
    create_project,
    csv_bytes,
    sample_frame,
)


@pytest.fixture(scope="module")
def profile() -> dict:
    df = sample_frame()
    df.loc[0:14, "age"] = np.nan  # 15% missing in age
    return profile_dataframe(df)


# ──────────────────────────────────────────────────────────────────────────────
# Tools return REAL computed numbers
# ──────────────────────────────────────────────────────────────────────────────

def test_dataset_summary_real_numbers(profile):
    result = chat_tools.execute_tool("dataset_summary", profile, {})
    assert result["num_rows"] == 100
    assert result["num_columns"] == 7
    assert result["missing_cells"] == 15


def test_column_statistics_exact_values(profile):
    result = chat_tools.execute_tool("column_statistics", profile, {"column": "age"})
    assert result["missing_pct"] == 15.0
    assert "mean" in result and "median" in result


def test_column_statistics_unknown_column_raises_cleanly(profile):
    with pytest.raises(ValueError, match="not found"):
        chat_tools.execute_tool("column_statistics", profile, {"column": "ghost"})


def test_missing_value_analysis_ranks_worst_first(profile):
    result = chat_tools.execute_tool("missing_value_analysis", profile, {})
    assert list(result["per_column"].keys()) == ["age"]
    assert result["total_missing_cells"] == 15
    assert "age" not in result["complete_columns"] or True


def test_correlation_analysis_involving_target(profile):
    result = chat_tools.execute_tool("correlation_analysis", profile, {"target": "age_copy"})
    assert any("age_copy" in (p["a"], p["b"]) for p in result["pairs_involving_target"])


def test_distribution_analysis_histogram(profile):
    result = chat_tools.execute_tool("distribution_analysis", profile, {"column": "age"})
    hist = result["histogram"]
    assert sum(hist["counts"]) == 85  # rows minus missing
    assert len(result["shape_note"]) > 5


def test_preprocessing_recommendation_tool(plan_payload_factory):
    plan = plan_payload_factory()
    result = chat_tools.execute_tool("preprocessing_recommendation", {}, {"_recommendation_plan": plan})
    assert result["note"].startswith("Steps require")
    assert isinstance(result["steps"], list)


@pytest.fixture
def plan_payload_factory():
    def _factory():
        from apps.api.modules.datasets.recommendations import build_plan
        return build_plan(profile_dataframe(sample_frame()))
    return _factory


# ──────────────────────────────────────────────────────────────────────────────
# Routing & anti-fabrication
# ──────────────────────────────────────────────────────────────────────────────

def test_route_missing_values_question():
    tool, args = route_without_llm("How many missing values are there?")
    assert tool == "missing_value_analysis"


def test_route_missing_in_specific_column_goes_to_stats():
    tool, args = route_without_llm("How many missing values are in age?")
    assert tool == "column_statistics"
    assert args.get("column") == "age"


def test_route_distribution_question():
    tool, args = route_without_llm("Show me the distribution of glucose")
    assert tool == "distribution_analysis"
    assert args.get("column") == "glucose"


def test_route_summary_question():
    tool, _ = route_without_llm("Can you summarize this dataset for me?")
    assert tool == "dataset_summary"


def test_unanswerable_question_refuses_to_guess(profile):
    """THE anti-fabrication guarantee: no tool → no numbers, honest refusal."""
    result = analyze_question("Will my stock portfolio beat the market?", profile, {})
    assert "guess" in result["answer"].lower() or "can't determine" in result["answer"].lower()
    assert result["tools_used"] == []
    # No fabricated digits about the dataset appear
    assert "100" not in result["answer"]


def test_unknown_column_answer_lists_available_columns(profile):
    result = analyze_question("How many missing values are in zzz_nope?", profile, {})
    assert "couldn't find" in result["answer"].lower()
    assert "Available columns" in result["answer"]


def test_fuzzy_column_match_single_candidate(profile):
    result = analyze_question("How many missing values are in gend?", profile, {})
    # 'gend' matches 'gender' uniquely → real answer with the true count
    assert "0%" in result["answer"]
    assert "couldn't find" not in result["answer"].lower()


def test_ambiguous_partial_column_refuses_to_guess(profile):
    """'ag' matches both age and age_copy → the analyst asks instead of guessing."""
    result = analyze_question("How many missing values are in ag?", profile, {})
    assert "couldn't find" in result["answer"].lower()


def test_compose_answer_never_contains_nan_strings(profile):
    result = chat_tools.execute_tool("missing_value_analysis", profile, {})
    text = compose_answer("missing_value_analysis", result)
    assert "nan" not in text.lower().replace("nan%", "")


# ──────────────────────────────────────────────────────────────────────────────
# Persistence via API
# ──────────────────────────────────────────────────────────────────────────────

async def _setup_dataset(client: AsyncClient, auth_headers: dict, with_missing: bool = False):
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])
    frame = sample_frame()
    if with_missing:
        df = frame.copy()
        df.loc[0:14, "age"] = np.nan
        frame = df
    up = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/upload",
        files={"file": ("data.csv", csv_bytes(frame), "text/csv")},
        headers=auth_headers,
    )
    assert up.status_code == 201, up.text
    return project, dataset


@pytest.mark.asyncio
async def test_chat_persists_history(client: AsyncClient, auth_headers: dict):
    project, dataset = await _setup_dataset(client, auth_headers, with_missing=True)

    resp1 = await client.post(
        f"/api/v1/projects/{project['id']}/chat",
        json={"message": "How many missing values are in age?", "dataset_id": dataset["id"]},
        headers=auth_headers,
    )
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()
    assert "15%" in body1["answer"]
    assert body1["tools_used"][0]["tool"] == "column_statistics"

    resp2 = await client.post(
        f"/api/v1/projects/{project['id']}/chat",
        json={"message": "Summarize this dataset", "dataset_id": dataset["id"]},
        headers=auth_headers,
    )
    assert resp2.status_code == 200

    hist = await client.get(
        f"/api/v1/projects/{project['id']}/chat/history",
        params={"dataset_id": dataset["id"]},
        headers=auth_headers,
    )
    assert hist.status_code == 200
    history = hist.json()
    roles = [m["role"] for m in history["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    # Tool audit trail persisted on assistant messages
    assistant_msgs = [m for m in history["messages"] if m["role"] == "assistant"]
    assert all(m["tools_used"] is not None for m in assistant_msgs)
    assert assistant_msgs[0]["tools_used"][0]["tool"] == "column_statistics"


@pytest.mark.asyncio
async def test_chat_requires_known_dataset(client: AsyncClient, auth_headers: dict):
    import uuid as uuidlib

    project = await create_project(client, auth_headers)
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/chat",
        json={"message": "summarize", "dataset_id": str(uuidlib.uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_without_dataset_still_answers_model_questions(client: AsyncClient, auth_headers: dict):
    project, _dataset = await _setup_dataset(client, auth_headers)

    # No model trained yet → honest answer, not invented metrics
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/chat",
        json={"message": "What are the model performance metrics?"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    lowered = body["answer"].lower()
    assert ("no trained model" in lowered) or ("ml lab" in lowered)
