import json

import pytest

from affordance_runtime.benchmarks.spec import BenchmarkRun
from affordance_runtime.contracts import ActionContract, RiskLevel
from affordance_runtime.evolution import (
    CandidateRuntimeProfile,
    EvolutionArtifact,
    EvolutionArtifactType,
    EvolutionRegistry,
    EvolutionRegistryStore,
    EvolutionStatus,
    FailureClass,
    FailureClassifier,
    MetricDirection,
    RecoveryPolicyPatchPayload,
    RecoverySkillPayload,
    RegressionRule,
    RuntimePatchPayload,
)
from affordance_runtime.recovery import FailureSignature, RecoveryAction, RecoveryContext


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


def test_executable_payload_loads_into_fresh_runtime_and_rolls_back(tmp_path) -> None:
    payload = RuntimePatchPayload(
        "1.0",
        "runtime_features",
        ["reversible_settings_update"],
        {"structural_verification": True},
    )
    artifact = EvolutionArtifact(
        "verifier-settings",
        EvolutionArtifactType.VERIFIER_PATCH.value,
        "enable structural verification",
        {},
        ["failed.jsonl"],
        status=EvolutionStatus.ACCEPTED,
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
    )
    registry = EvolutionRegistry({artifact.id: artifact})
    store = EvolutionRegistryStore(tmp_path / "registry.json")
    store.save(registry)
    persisted = store.load()
    profile = CandidateRuntimeProfile()
    profile.load(persisted.artifacts[artifact.id])

    assert profile.features_for("reversible_settings_update").structural_verification
    assert not profile.features_for("read_only_evidence_chain").structural_verification
    profile.rollback(artifact.id)
    assert not profile.features_for("reversible_settings_update").structural_verification
    assert json.loads(store.path.read_text())["schema_version"] == "1.0"


def test_candidate_runtime_rejects_tampered_or_rolled_back_payload() -> None:
    payload = RuntimePatchPayload("1.0", "runtime_features", ["settings"], {"structural_verification": True})
    artifact = EvolutionArtifact(
        "verifier-settings",
        EvolutionArtifactType.VERIFIER_PATCH.value,
        "patch",
        {},
        ["failed.jsonl"],
        status=EvolutionStatus.ACCEPTED,
        payload=payload.to_dict(),
        payload_digest="wrong",
    )
    with pytest.raises(ValueError, match="digest mismatch"):
        CandidateRuntimeProfile().load(artifact)

    artifact.payload_digest = payload.digest()
    artifact.status = EvolutionStatus.ROLLED_BACK
    with pytest.raises(ValueError, match="only accepted"):
        CandidateRuntimeProfile().load(artifact)

    unsafe_payload = RuntimePatchPayload("1.0", "runtime_features", ["settings"], {"capability_gate": False})
    artifact.status = EvolutionStatus.ACCEPTED
    artifact.payload = unsafe_payload.to_dict()
    artifact.payload_digest = unsafe_payload.digest()
    with pytest.raises(ValueError, match="may only enable structural verification"):
        CandidateRuntimeProfile().load(artifact)


def _recovery_contract() -> ActionContract:
    return ActionContract("contract", "save", "save", "click", "dom", "rev", {"selector": "#save"})


def _failure_signature() -> FailureSignature:
    return FailureSignature("acting", "timeout <n>", "execution_failed", "click", "dom", "target", "", "rev")


def test_recovery_policy_patch_loads_matches_and_rolls_back() -> None:
    payload = RecoveryPolicyPatchPayload(
        "1.0",
        "recovery_policy",
        ["settings"],
        {"error_code": "execution_failed", "action": "click"},
        "abort",
        1,
        ["events.jsonl"],
        ["loop_stopped"],
    )
    artifact = EvolutionArtifact(
        "policy-settings-loop",
        EvolutionArtifactType.POLICY_PATCH.value,
        "stop repeated settings loop",
        {},
        ["failed.jsonl"],
        status=EvolutionStatus.ACCEPTED,
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
    )
    profile = CandidateRuntimeProfile()
    profile.load(artifact)
    decision = profile.recovery_policy().decide(
        _recovery_contract(),
        None,
        RecoveryContext(failure_signature=_failure_signature(), task_id="settings"),
    )
    assert decision.action == RecoveryAction.ABORT
    profile.rollback(artifact.id)
    fallback = profile.recovery_policy().decide(
        _recovery_contract(),
        None,
        RecoveryContext(failure_signature=_failure_signature(), task_id="settings"),
    )
    assert fallback.action == RecoveryAction.ABORT  # non-idempotent built-in default, no artifact reason
    assert "declarative" not in fallback.reason


def test_recovery_skill_is_bounded_and_preserves_uncertain_effect_inspection() -> None:
    payload = RecoverySkillPayload(
        "1.0",
        "recovery_skill",
        ["settings"],
        {"normalized_error": "timeout <n>"},
        ["reobserve", "abort"],
        2,
        ["post_state"],
        ["state_changed_or_abort"],
        max_risk=RiskLevel.MEDIUM.value,
    )
    artifact = EvolutionArtifact(
        "skill-settings-timeout",
        EvolutionArtifactType.SKILL.value,
        "bounded timeout inspection",
        {},
        ["failed.jsonl"],
        status=EvolutionStatus.ACCEPTED,
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
    )
    profile = CandidateRuntimeProfile()
    profile.load(artifact)
    policy = profile.recovery_policy()
    context = RecoveryContext(failure_signature=_failure_signature(), task_id="settings")
    assert policy.decide(_recovery_contract(), None, context).action == RecoveryAction.REOBSERVE
    assert policy.decide(_recovery_contract(), None, context).action == RecoveryAction.ABORT
    uncertain = RecoveryContext(
        failure_signature=_failure_signature(),
        task_id="settings",
        effect_may_have_occurred=True,
    )
    assert policy.decide(_recovery_contract(), None, uncertain).action == RecoveryAction.VERIFY_STATE


def test_recovery_artifacts_reject_blind_retry_payload() -> None:
    payload = RecoveryPolicyPatchPayload(
        "1.0",
        "recovery_policy",
        ["settings"],
        {"error_code": "execution_failed"},
        "retry",
        1,
        ["receipt"],
        ["saved"],
    )
    with pytest.raises(ValueError, match="blind retry"):
        payload.validate()
