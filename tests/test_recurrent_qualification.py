import asyncio
from pathlib import Path

from test_compact_grounding_matrix_runner import ContextFollowingPort

from affordance_runtime.benchmarks.model_conformance.contracts import ModelProfileIdentity
from affordance_runtime.benchmarks.model_conformance.matrix_runner import run_decision_matrix
from affordance_runtime.benchmarks.model_conformance.recurrent_qualification import (
    qualify_recurrent_result,
)
from affordance_runtime.model_policy.grounding import DecisionGroundingVariant


def _identity() -> ModelProfileIdentity:
    return ModelProfileIdentity(
        "fixture", "recurrent", "local", "fixture", "1", "digest", "family", "1B", "Q4",
        "p5-m1.1", "agent-decision.v1", "default-64k", "sha256:schema", 1_024,
        "compact-contract-v2", "compact-contract.v2", "fixture", "compact-contract.v2", "",
    )


def test_scripted_v2_candidate_closes_seven_runtime_and_critical_cases(tmp_path: Path) -> None:
    result = asyncio.run(run_decision_matrix(
        _identity(), ContextFollowingPort, repetitions=5, output_dir=tmp_path,
        grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT_V2,
    ))
    qualification = qualify_recurrent_result(result, support_attestation=False)
    assert qualification.admitted and qualification.status == "candidate_passed"
    assert all(passed == total == 5 for _, passed, total in qualification.decision_success_counts)
    assert all(passed == total == 5 for _, passed, total in qualification.critical_success_counts)
    assert qualification.runtime_success_count == 7
    assert qualification.retry_count == qualification.fallback_count == 0
