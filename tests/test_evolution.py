from affordance_runtime.benchmarks.spec import BenchmarkRun
from affordance_runtime.evolution import (
    EvolutionArtifact,
    EvolutionRegistry,
    EvolutionStatus,
    FailureClass,
    FailureClassifier,
    MetricDirection,
    RegressionRule,
)


def test_regression_gate_respects_metric_direction() -> None:
    artifact = EvolutionArtifact(
        id="patch-1",
        artifact_type="verifier",
        summary="improve structural check",
        applicability={"suite": "pricing"},
        source_traces=["run-1"],
        regression_results={"task_success_rate": 0.95, "unsafe_side_effect_rate": 0.0},
    )
    registry = EvolutionRegistry({artifact.id: artifact})

    status = registry.accept_if_regression_passes(
        artifact.id,
        rules=[
            RegressionRule("task_success_rate", MetricDirection.HIGHER_IS_BETTER, 0.9),
            RegressionRule("unsafe_side_effect_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
        ],
    )

    assert status == EvolutionStatus.ACCEPTED


def test_regression_gate_quarantines_missing_or_regressed_metric() -> None:
    artifact = EvolutionArtifact(
        id="patch-2",
        artifact_type="policy",
        summary="unsafe candidate",
        applicability={},
        source_traces=["run-2"],
        regression_results={"unsafe_side_effect_rate": 0.1},
    )
    registry = EvolutionRegistry({artifact.id: artifact})

    status = registry.accept_if_regression_passes(
        artifact.id,
        rules=[
            RegressionRule("unsafe_side_effect_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
            RegressionRule("task_success_rate", MetricDirection.HIGHER_IS_BETTER, 0.9),
        ],
    )

    assert status == EvolutionStatus.QUARANTINED
    assert "missing metrics" in artifact.decision_reason
    assert "failed metrics" in artifact.decision_reason


def test_failure_classifier_maps_false_accept_to_verification_patch() -> None:
    run = BenchmarkRun(
        "settings",
        False,
        1,
        10.0,
        verifier_false_accepts=1,
        failed_outcomes=1,
        variant="no_structural_verifier",
        trace_path="trace.jsonl",
    )

    classifier = FailureClassifier()
    proposal = classifier.propose(run)

    assert classifier.classify_run(run) == FailureClass.VERIFICATION
    assert proposal.artifact_type.value == "verifier_patch"
    assert proposal.source_trace == "trace.jsonl"


def test_registry_rejects_duplicate_version_and_supports_rollback() -> None:
    artifact = EvolutionArtifact("patch", "policy", "summary", {}, ["run"])
    registry = EvolutionRegistry()
    registry.propose(artifact)
    artifact.regression_results = {"safety": 0.0}
    registry.accept_if_regression_passes(
        artifact.id,
        rules=[RegressionRule("safety", MetricDirection.LOWER_IS_BETTER, 0.0)],
    )

    try:
        registry.propose(EvolutionArtifact("patch", "policy", "duplicate", {}, ["run-2"]))
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("duplicate artifact version should fail")

    assert registry.rollback("patch", reason="regression detected", reviewer="maintainer") == EvolutionStatus.ROLLED_BACK


def test_registry_preserves_previous_artifact_versions() -> None:
    registry = EvolutionRegistry()
    registry.propose(EvolutionArtifact("patch", "policy", "v1", {}, ["run-1"], version="1.0.0"))
    registry.propose(EvolutionArtifact("patch", "policy", "v2", {}, ["run-2"], version="2.0.0"))

    assert registry.artifacts["patch"].version == "2.0.0"
    assert [item.version for item in registry.history["patch"]] == ["1.0.0"]
