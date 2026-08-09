import asyncio
import json
from pathlib import Path

import pytest

from affordance_runtime.benchmarks.model_conformance.contracts import ModelProfileIdentity
from affordance_runtime.benchmarks.model_conformance.two_stage.attestation import attest_two_stage
from affordance_runtime.benchmarks.model_conformance.two_stage.contracts import PacingConfiguration
from affordance_runtime.benchmarks.model_conformance.two_stage.suite import run_candidate_suite
from tests.test_two_stage_runner import SemanticFollowingPort


def _identity() -> ModelProfileIdentity:
    return ModelProfileIdentity(
        "fixture", "model", "local", "fixture", "1", "digest", "family", "1B", "Q4",
        "p5-m3.6", "agent-decision.v1", "default-64k", "sha256:schema", 1_024,
        "compact-contract-v2", "compact-contract.v2", "fixture",
        "compact-contract.v2", "",
    )


def test_candidate_suite_reports_all_four_comparisons_and_attests(tmp_path: Path) -> None:
    report = asyncio.run(run_candidate_suite(
        _identity(), SemanticFollowingPort, repetitions=5, output_dir=tmp_path,
        pacing=PacingConfiguration(),
    ))
    assert report.baseline.success_count == 35
    assert report.routing.success_count == 35
    assert report.payload.success_count == 35
    assert report.end_to_end.success_count == 35
    assert report.critical.success_count == 40
    assert report.qualification.admitted is True
    qualification = tmp_path / "qualification.json"
    qualification.write_text(json.dumps({"admitted": True}))
    attestation = attest_two_stage(
        report, (tmp_path / "suite-report.json", qualification),
        git_sha="a" * 40, git_dirty=False,
    )
    assert attestation.accepted is True
    assert attestation.provider_calls == 255
    assert attestation.retry_count == attestation.fallback_count == 0


def test_candidate_output_directory_is_never_resumed_or_overwritten(tmp_path: Path) -> None:
    tmp_path.joinpath("partial.json").write_text("{}")
    with pytest.raises(ValueError, match="new empty output"):
        asyncio.run(run_candidate_suite(
            _identity(), SemanticFollowingPort, repetitions=5, output_dir=tmp_path,
            pacing=PacingConfiguration(),
        ))
