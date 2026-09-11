"""Target-feature suggestion tests (user-requested feature)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.api.modules.automl.task_detection import detect_task, suggest_targets
from apps.api.modules.datasets.profiling import profile_dataframe


def frame_with_candidates() -> pd.DataFrame:
    rng = np.random.default_rng(9)
    n = 200
    return pd.DataFrame({
        "row_id": range(1, n + 1),
        "age": rng.normal(40, 10, n).round(1),
        "plan": rng.choice(["basic", "pro", "enterprise"], n),
        "churned": rng.choice([0, 1], n, p=[0.8, 0.2]),
        "revenue": np.abs(rng.normal(500, 120, n)).round(2),
        "notes": ["free text"] * n,
    })


def profile_of(df: pd.DataFrame) -> dict:
    return profile_dataframe(df)


def test_name_match_ranks_first():
    df = frame_with_candidates()
    df["target"] = df["plan"]
    ranked = suggest_targets(profile_of(df))
    assert ranked[0]["column"] == "target"
    assert ranked[0]["confidence"] == "high"


def test_identifiers_and_constants_excluded():
    df = frame_with_candidates()
    df["constant"] = "same"
    ranked = suggest_targets(profile_of(df))
    cols = {r["column"] for r in ranked}
    assert "row_id" not in cols
    assert "constant" not in cols


def test_low_cardinality_beats_continuous():
    ranked = suggest_targets(profile_of(frame_with_candidates()))
    # churned (binary) should outrank revenue (continuous regression guess)
    order = [r["column"] for r in ranked]
    if "revenue" in order:
        assert order.index("churned") < order.index("revenue")
    else:
        # capped list: binary label must at least make the cut
        assert "churned" in order[:2]
    assert order[0] in ("plan", "churned")


def test_continuous_only_dataset_still_suggests_regression():
    rng = np.random.default_rng(4)
    df = pd.DataFrame({
        "x1": rng.normal(0, 1, 150).round(3),
        "price": rng.lognormal(3, 0.5, 150).round(2),
    })
    ranked = suggest_targets(profile_of(df))
    assert ranked, "continuous dataset must still produce a suggestion"
    assert all(r["task_type"] == "regression" for r in ranked)


def test_ranking_is_sequential_and_capped():
    ranked = suggest_targets(profile_of(frame_with_candidates()), limit=3)
    assert len(ranked) <= 3
    assert [r["rank"] for r in ranked] == list(range(1, len(ranked) + 1))


def test_detect_without_target_returns_suggestions():
    result = detect_task(profile_of(frame_with_candidates()), None)
    assert result["task_type"] == "unsupervised"
    assert len(result["suggested_targets"]) >= 1
    first = result["suggested_targets"][0]
    assert first["reason"] and first["task_type"]


def test_heavily_missing_column_not_suggested():
    df = frame_with_candidates()
    df.loc[0:180, "plan"] = None  # 90% missing
    ranked = suggest_targets(profile_of(df))
    assert all(r["column"] != "plan" for r in ranked)


# ── API wiring ────────────────────────────────────────────────────────────────

from httpx import AsyncClient  # noqa: E402

from apps.api.modules.datasets.tests.test_ingestion import (  # noqa: E402
    create_dataset,
    create_project,
    csv_bytes,
    sample_frame,
)


@pytest.mark.asyncio
async def test_endpoint_returns_suggested_targets(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])
    up = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/upload",
        files={"file": ("data.csv", csv_bytes(sample_frame()), "text/csv")},
        headers=auth_headers,
    )
    version_id = up.json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{version_id}/task-detection",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    names = [s["column"] for s in body["suggested_targets"]]
    assert "target" in names          # name match must be present & first
    assert names[0] == "target"
    assert body["suggested_targets"][0]["confidence"] == "high"
