from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from affordance_runtime.benchmarks.generalization_evidence import (
    GeneralizationProfileKind,
)
from affordance_runtime.benchmarks.generalization_rollout import (
    run_generalization_runtime_rollout,
)


def test_four_profile_rollout_derives_report_from_real_runtime_artifacts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "g5-rollout"

    report = run_generalization_runtime_rollout(output, revision="revision-test-g5")

    assert report.acceptance == "passed"
    assert report.acceptance_errors == ()
    assert report.official_score_claimed is False
    assert {item.kind for item in report.profiles} == set(GeneralizationProfileKind)
    assert len(report.cases) == 11
    assert all(
        Path(ref).is_file()
        for case in report.cases
        for ref in case.evidence_refs
    )
    comparisons = {item.candidate: item for item in report.comparisons}
    assert (
        comparisons[GeneralizationProfileKind.STRICT_PLUS_ACCEPTED_SKILLS]
        .planner_call_reduction
        > 0
    )
    assert (
        comparisons[GeneralizationProfileKind.HISTORICAL_COMPATIBILITY]
        .task_success_delta
        > 0
    )
    assert (
        comparisons[GeneralizationProfileKind.DECLARED_ABLATIONS]
        .task_success_delta
        < 0
    )

    manifest = json.loads((output / "rollout-manifest.json").read_text())
    assert manifest["revision"] == "revision-test-g5"
    assert manifest["remote_model_used"] is False
    assert manifest["official_score_claimed"] is False
    assert manifest["artifact_index"]
    for relative, expected in manifest["artifact_index"].items():
        digest = hashlib.sha256((output / relative).read_bytes()).hexdigest()
        assert expected == f"sha256:{digest}"


def test_four_profile_rollout_refuses_to_overwrite_an_immutable_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "g5-rollout"
    run_generalization_runtime_rollout(output, revision="revision-test-g5")

    with pytest.raises(FileExistsError, match="already exists"):
        run_generalization_runtime_rollout(output, revision="revision-test-g5")
