import hashlib
from dataclasses import replace

import pytest

from affordance_runtime.contracts import Observation
from affordance_runtime.evolution import (
    AcceptedProfileLoader,
    CandidateRuntimeProfile,
    EvolutionRegistry,
    EvolutionRegistryStore,
    EvolutionStatus,
)
from affordance_runtime.grounding import GroundingSource, UnifiedAffordance
from affordance_runtime.runtime import legacy_run_request
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.task_skills import (
    IncrementalTaskSkillExecutor,
    SemanticTargetQuery,
    SkillParameterType,
    TaskSkillMiner,
    TaskSkillPayload,
    TaskSkillProgress,
    TaskSkillReplayDecision,
    TaskSkillReplayEvidence,
    TaskSkillReplayGate,
    VerifiedSemanticStep,
    VerifiedSemanticTrace,
    quarantine_task_skill,
)
from affordance_runtime.unified_observation import (
    ActionSupport,
    CanonicalTarget,
    ConflictStatus,
    Freshness,
    UnifiedObservation,
)
from affordance_runtime.verification.contracts import SuccessExpression
from runtime_test_support import remember_observation


def _canonical_skill_observation(
    observation: Observation,
    target: UnifiedAffordance,
) -> UnifiedObservation:
    binding_id = f"binding:{target.semantic_target_id}"
    return UnifiedObservation(
        snapshot_id=observation.snapshot_id,
        page_revision=observation.page_revision,
        environment_revision=observation.environment_revision,
        observed_text="",
        targets=(
            CanonicalTarget(
                target_id=target.semantic_target_id,
                role=target.role,
                label=target.label,
                surfaces=(GroundingSource.DOM,),
                action_support=tuple(
                    ActionSupport(action, (binding_id,)) for action in sorted(target.supported_actions)
                ),
                state_facts=(),
                binding_ids=(binding_id,),
                conflict_status=ConflictStatus.NO_MATERIAL_CONFLICT,
                conflicts=(),
                source_assertion_refs=(),
                freshness=Freshness(
                    observation.snapshot_id,
                    observation.environment_revision,
                    observation.page_revision,
                    observation.observed_at_s,
                ),
            ),
        ),
    )


def _trace(index: int, variant: str, label: str, value: str) -> VerifiedSemanticTrace:
    return VerifiedSemanticTrace(
        trace_id=f"trace-{index}",
        task_family="profile update",
        variant=variant,
        objective=f"Set {label} to {value}",
        steps=(
            VerifiedSemanticStep(
                "type_text",
                "textbox",
                label,
                parameters=(("text", value),),
                postconditions=("profile value changed",),
                evidence_requirements=("independent control state",),
            ),
        ),
    )


def _payload() -> TaskSkillPayload:
    return TaskSkillMiner().mine(
        (
            _trace(1, "layout-a", "Name", "Ada"),
            _trace(2, "layout-b", "Full name", "Grace"),
            _trace(3, "layout-a", "Name", "Linus"),
        ),
        skill_id="profile.update-name",
        heldout_suite="profile-heldout-v1",
    )


def test_task_skill_miner_extracts_typed_slots_from_verified_variant_traces() -> None:
    payload = _payload()

    assert payload.parameters[0].name == "step_1_target_label"
    assert payload.parameters[0].value_type == SkillParameterType.STRING
    assert payload.parameters[1].name == "step_1_text"
    assert payload.steps[0].target_query.label_template == "{{step_1_target_label}}"
    assert payload.steps[0].parameter_bindings == (("text", "step_1_text"),)
    assert len(payload.source_traces) == 3
    assert len(set(payload.source_variants)) == 2
    assert payload.digest() == TaskSkillPayload.from_dict(payload.to_dict()).digest()


def test_task_skill_rejects_raw_backend_handles_and_unverified_sources() -> None:
    payload = _payload()
    unsafe_step = replace(
        payload.steps[0],
        target_query=SemanticTargetQuery("textbox", "selector=#name", "type_text"),
    )
    with pytest.raises(ValueError, match="forbidden raw handle"):
        replace(payload, steps=(unsafe_step,)).validate()

    unsafe_trace = replace(_trace(4, "layout-c", "Name", "Ken"), independently_verified=False)
    with pytest.raises(ValueError, match="not independently safe and verified"):
        TaskSkillMiner().mine(
            (_trace(1, "layout-a", "Name", "Ada"), _trace(2, "layout-b", "Name", "Grace"), unsafe_trace),
            skill_id="profile.unsafe-name",
            heldout_suite="profile-heldout-v1",
        )


def test_task_skill_candidate_is_quarantined_and_digest_gated_before_loading() -> None:
    payload = _payload()
    registry = EvolutionRegistry()

    artifact = quarantine_task_skill(payload, registry)

    assert artifact.status == EvolutionStatus.QUARANTINED
    assert registry.artifacts[payload.skill_id].payload_digest == payload.digest()
    with pytest.raises(ValueError, match="only accepted artifacts"):
        CandidateRuntimeProfile().load(artifact)

    artifact.status = EvolutionStatus.ACCEPTED
    profile = CandidateRuntimeProfile()
    profile.load(artifact)
    assert profile.task_skills_for("profile update") == (payload,)
    profile.rollback(artifact.id)
    assert not profile.task_skills_for("profile update")


def test_accepted_profile_loader_binds_registry_digest_and_ignores_nonaccepted(tmp_path) -> None:
    registry = EvolutionRegistry()
    accepted = quarantine_task_skill(_payload(), registry)
    accepted.status = EvolutionStatus.ACCEPTED
    quarantined_payload = replace(_payload(), skill_id="profile.pending-name", version="1.0.1")
    quarantine_task_skill(quarantined_payload, registry)
    path = tmp_path / "accepted-registry.json"
    EvolutionRegistryStore(path).save(registry)

    loaded = AcceptedProfileLoader(path).load()

    assert loaded.profile_digest.startswith("sha256:")
    assert loaded.artifact_ids == (accepted.id,)
    assert loaded.task_skill_runtime is not None
    assert tuple(loaded.profile.loaded) == (accepted.id,)


def test_accepted_profile_loader_rejects_payload_digest_mismatch(tmp_path) -> None:
    registry = EvolutionRegistry()
    artifact = quarantine_task_skill(_payload(), registry)
    artifact.status = EvolutionStatus.ACCEPTED
    artifact.payload["skill_id"] = "profile.tampered-name"
    path = tmp_path / "tampered-registry.json"
    EvolutionRegistryStore(path).save(registry)

    with pytest.raises(ValueError, match="payload digest mismatch"):
        AcceptedProfileLoader(path).load()


def test_rolled_back_artifact_is_absent_from_a_fresh_profile(tmp_path) -> None:
    registry = EvolutionRegistry()
    artifact = quarantine_task_skill(_payload(), registry)
    artifact.status = EvolutionStatus.ACCEPTED
    registry.rollback(artifact.id, reason="heldout regression", reviewer="test-reviewer")
    path = tmp_path / "rolled-back-registry.json"
    EvolutionRegistryStore(path).save(registry)

    with pytest.raises(ValueError, match="no accepted artifacts"):
        AcceptedProfileLoader(path).load()


def test_incremental_task_skill_exposes_one_current_semantic_step_and_checkpoints_only_verification() -> None:
    payload = _payload()
    observation = Observation("rev-1", snapshot_id="snap-1", page_revision="page-1")
    target = UnifiedAffordance(
        "semantic:full-name",
        "textbox",
        "Full name",
        frozenset({"type_text"}),
    )
    canonical = _canonical_skill_observation(observation, target)
    state = StateKernel("profile-task", "Set Full name to Margaret")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="profile-task",
        revision=1,
        objective="Set Full name to Margaret",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(("Full name",), OperationClass.REVERSIBLE_WRITE, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("Full name",)),
        success=SuccessExpression(
            expression_id="success:full-name",
            operator="criterion",
            criterion_id="criterion:full-name",
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref="test",
    )
    bindings = {
        "step_1_target_label": "Full name",
        "step_1_text": "Margaret",
    }
    progress = TaskSkillProgress(payload.skill_id, payload.version)
    executor = IncrementalTaskSkillExecutor()

    exposure = executor.expose_next(payload, bindings, task, state, canonical, progress)

    assert exposure.proposal is not None
    assert exposure.proposal.target_affordance_id == "semantic:full-name"
    assert exposure.proposal.parameters == {"text": "Margaret"}
    assert progress.next_step_index == 0
    executor.checkpoint_verified(payload, progress, step_id="step-1", verified=False)
    assert progress.next_step_index == 0
    assert progress.completed_step_ids == []
    executor.checkpoint_verified(
        payload,
        progress,
        step_id="step-1",
        verified=True,
        evidence=("artifact:post-state",),
    )
    assert progress.next_step_index == 1
    assert progress.completed_step_ids == ["step-1"]
    assert progress.evidence == ["artifact:post-state"]
    assert executor.expose_next(payload, bindings, task, state, canonical, progress).proposal is None


def test_task_skill_mismatch_falls_through_without_losing_verified_progress() -> None:
    payload = _payload()
    observation = Observation("rev-1", snapshot_id="snap-1", page_revision="page-1")
    target = UnifiedAffordance("semantic:other", "textbox", "Other", frozenset({"type_text"}))
    state = StateKernel("profile-task", "Set Full name")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="profile-task",
        revision=1,
        objective="Set Full name",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(("Full name",), OperationClass.REVERSIBLE_WRITE, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("Full name",)),
        success=SuccessExpression(
            expression_id="success:full-name",
            operator="criterion",
            criterion_id="criterion:full-name",
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref="test",
    )
    progress = TaskSkillProgress(
        payload.skill_id,
        payload.version,
        completed_step_ids=["prior-step"],
        evidence=["artifact:prior"],
    )

    exposure = IncrementalTaskSkillExecutor().expose_next(
        payload,
        {"step_1_target_label": "Full name", "step_1_text": "Ada"},
        task,
        state,
        _canonical_skill_observation(observation, target),
        progress,
    )

    assert exposure.fallthrough
    assert exposure.proposal is None
    assert progress.completed_step_ids == ["prior-step"]
    assert progress.evidence == ["artifact:prior"]
    assert "matched 0" in progress.fallthrough_reason


def test_task_skill_types_do_not_change_task_authority() -> None:
    payload = _payload()
    assert all(not step.required_capabilities for step in payload.steps)
    assert legacy_run_request(task_id="run", goal="profile update").capabilities == []


def _replay(category: str, *, activated: bool = True, applicable: bool = True) -> TaskSkillReplayEvidence:
    evidence = TaskSkillReplayEvidence(
        category,
        f"replay-{category}",
        f"variant-{category}",
        True,
        True,
        activated,
        applicable,
        model_calls=1 if activated else 2,
        latency_ms=20.0,
        source_trace_digest=_digest(f"trace:{category}"),
        skill_payload_digest=_payload().digest(),
    )
    return replace(evidence, replay_report_digest=evidence.canonical_report_digest())


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def test_task_skill_replay_decision_metrics_are_immutable_from_source_mapping() -> None:
    metrics = {"activation_rate_delta": 0.25}

    decision = TaskSkillReplayDecision(
        status="accepted",
        reason="complete safe replay",
        metrics=metrics,
    )
    metrics["activation_rate_delta"] = 0.0

    assert decision.metrics["activation_rate_delta"] == 0.25
    with pytest.raises(TypeError):
        decision.metrics["activation_rate_delta"] = 0.0


def test_task_skill_replay_gate_accepts_only_complete_safe_heldout_efficiency_evidence() -> None:
    registry = EvolutionRegistry()
    artifact = quarantine_task_skill(_payload(), registry)
    evidence = (
        _replay("original"),
        _replay("task_family"),
        _replay("heldout"),
        _replay("global_smoke", activated=False, applicable=False),
        _replay("safety_smoke", activated=False, applicable=False),
    )

    decision = TaskSkillReplayGate().evaluate(
        registry,
        artifact.id,
        evidence,
        baseline_model_calls=3.0,
        baseline_latency_ms=50.0,
    )

    assert decision.status == EvolutionStatus.ACCEPTED.value
    assert decision.metrics["task_success_rate"] == 1.0
    assert decision.metrics["skill_activation_precision"] == 1.0
    assert decision.metrics["model_call_reduction"] > 0


def test_task_skill_replay_gate_keeps_missing_heldout_or_efficiency_in_quarantine() -> None:
    registry = EvolutionRegistry()
    artifact = quarantine_task_skill(_payload(), registry)
    evidence = (
        _replay("original"),
        _replay("task_family"),
        _replay("global_smoke", activated=False, applicable=False),
        _replay("safety_smoke", activated=False, applicable=False),
    )

    decision = TaskSkillReplayGate().evaluate(
        registry,
        artifact.id,
        evidence,
        baseline_model_calls=1.0,
        baseline_latency_ms=20.0,
    )

    assert decision.status == EvolutionStatus.QUARANTINED.value
    assert "heldout" in decision.reason
    assert "did not reduce" in decision.reason


def test_task_skill_replay_gate_rejects_unbound_or_reused_reports() -> None:
    registry = EvolutionRegistry()
    artifact = quarantine_task_skill(_payload(), registry)
    evidence = tuple(
        replace(
            _replay(
                category,
                activated=category not in {"global_smoke", "safety_smoke"},
                applicable=category not in {"global_smoke", "safety_smoke"},
            ),
            replay_report_digest=_digest("one-reused-report"),
        )
        for category in ("original", "task_family", "heldout", "global_smoke", "safety_smoke")
    )

    decision = TaskSkillReplayGate().evaluate(
        registry,
        artifact.id,
        evidence,
        baseline_model_calls=3.0,
        baseline_latency_ms=50.0,
    )

    assert decision.status == EvolutionStatus.QUARANTINED.value
    assert "independently digest-bound" in decision.reason
