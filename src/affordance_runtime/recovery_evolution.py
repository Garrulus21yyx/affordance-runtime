"""Executable M8.3 recovery-cascade evolution gate."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from affordance_runtime.action_contract_builder import ActionContractMaterializer
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.evolution import (
    CandidateRuntimeProfile,
    EvolutionArtifact,
    EvolutionArtifactType,
    EvolutionRecoveryAction,
    EvolutionRecoveryContext,
    EvolutionRegistry,
    EvolutionRegistryStore,
    EvolutionStatus,
    MetricDirection,
    RecoveryPolicyPatchPayload,
    RegressionRule,
)
from affordance_runtime.immutable import FrozenSequence, freeze_json, to_json_compatible
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import PlannerDoneResponse, PlannerProposalResponse, PlannerResponse
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.verification.contracts import SuccessExpression

MANDATORY_RECOVERY_REPLAYS = {"original", "task_family", "global_smoke", "safety_smoke"}


def _snapshot(*, effect_verified: bool = False, sequence: int = 1) -> BrowserSnapshot:
    revision = "recovery-state-v1"
    snapshot_id = f"recovery-snapshot-v{sequence}"
    model = DomAdapter().transduce(
        '<button id="save">Save</button>',
        environment_revision=revision,
        snapshot_id=snapshot_id,
        page_revision=revision,
    )
    return BrowserSnapshot(
        Observation(
            revision,
            snapshot_id=snapshot_id,
            page_revision=revision,
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
            metadata={
                "effect_verified": effect_verified,
                "criterion_evaluations": {
                    "criterion:recovery-effect-verified": ("satisfied" if effect_verified else "unsatisfied")
                },
            },
        ),
        model,
    )


@dataclass
class RecoveryFixtureWorld:
    effect_verified: bool = False


@dataclass
class StableRecoveryObserver:
    world: RecoveryFixtureWorld = field(default_factory=RecoveryFixtureWorld)
    captures: int = 0

    def capture(self) -> BrowserSnapshot:
        self.captures += 1
        return _snapshot(
            effect_verified=self.world.effect_verified,
            sequence=self.captures,
        )


@dataclass
class RecoveryFixturePlanner:
    idempotent: bool

    def propose(self, request: PlanningRequest) -> PlannerResponse:
        if any(item.receipt_status == "success" for item in request.recent_outcomes):
            return PlannerDoneResponse(result={"effect": "verified"})
        target = request.observation.affordances[0]
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id=f"recovery-fixture-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal="exercise bounded recovery",
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=target.target_id,
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="recovery-fixture-planner",
                profile_id="recovery-evolution",
            ),
        )


@dataclass
class RecoveryFixtureExecutor:
    mode: str
    world: RecoveryFixtureWorld = field(default_factory=RecoveryFixtureWorld)
    backend: str = "dom"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        if self.mode == "success":
            self.world.effect_verified = True
            return ExecutionReceipt(
                contract.id,
                self.backend,
                True,
                observation.environment_revision,
                observation.environment_revision,
                1.0,
                evidence={"effect_verified": True},
            )
        code = RuntimeErrorCode.EXECUTION_TIMEOUT if self.mode == "uncertain" else RuntimeErrorCode.EXECUTION_FAILED
        return ExecutionReceipt(
            contract.id,
            self.backend,
            False,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence={"dispatched": False},
            error_code=code,
            message=(
                "Timeout 5000 after dispatch; effect outcome unknown"
                if self.mode == "uncertain"
                else "Transient backend failure 503 on attempt 42"
            ),
        )


@dataclass(frozen=True)
class RecoveryReplayEvidence:
    category: str
    task_id: str
    runtime_status: str
    cascade_depth: int
    recovery_actions: list[str]
    loop_aborts: int
    duplicate_effect_risks: int
    unsafe_side_effects: int
    passed: bool
    trace_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "recovery_actions", FrozenSequence(self.recovery_actions))


@dataclass(frozen=True)
class RecoveryEvolutionReport:
    source_incident: dict[str, Any]
    artifact: EvolutionArtifact
    replays: list[RecoveryReplayEvidence]
    decision: EvolutionStatus
    quarantined_before_replay: bool
    fresh_candidate_id: str
    registry_path: str
    quarantine_registry_path: str
    rollback_proof_path: str
    rollback_verified: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_incident", freeze_json(self.source_incident))
        object.__setattr__(self, "replays", FrozenSequence(self.replays))


def run_recovery_cascade_evolution(output_dir: Path) -> RecoveryEvolutionReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = _run_fixture(
        "recovery-original",
        mode="repeated",
        idempotent=True,
        artifact_root=output_dir / "baseline",
    )
    failure = baseline.state.current_failure
    if failure is None or baseline.status != RuntimeStep.ABORTED:
        raise RuntimeError("source run did not produce a real repeated recovery failure")
    signature = SimpleNamespace(
        error_code=failure.error_code,
        action="",
        backend="",
        normalized_error=failure.message,
        phase=failure.phase.value,
    )

    payload = RecoveryPolicyPatchPayload(
        schema_version="1.0",
        patch_kind="recovery_policy",
        task_ids=["recovery-original", "recovery-family"],
        signature_match={
            "error_code": failure.error_code,
            "phase": failure.phase.value,
            "normalized_error": failure.message,
        },
        response=EvolutionRecoveryAction.ABORT.value,
        max_applications=1,
        required_evidence=["failure_signature", "state_revision", "events.jsonl"],
        postconditions=["no_second_effect_attempt", "cascade_depth_lte_1"],
    )
    payload.validate()
    artifact = EvolutionArtifact(
        id="recovery-policy-repeated-backend-failure",
        artifact_type=EvolutionArtifactType.POLICY_PATCH.value,
        summary="Abort a known no-progress backend failure before a duplicate retry",
        applicability={"tasks": payload.task_ids, "signature": payload.signature_match},
        source_traces=[_trace_path(baseline)],
        negative_examples=[failure.failure_id],
        status=EvolutionStatus.QUARANTINED,
        source_runtime_version="0.1.0",
        target_suite_versions=["recovery-cascade-v1"],
        rollback_artifact="built-in-bounded-recovery-policy",
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
        decision_reason="quarantined pending fresh mandatory replay",
    )
    registry = EvolutionRegistry()
    registry.propose(artifact)
    quarantine_path = output_dir / "quarantined-registry.json"
    EvolutionRegistryStore(quarantine_path).save(registry)
    quarantined_before = (
        EvolutionRegistryStore(quarantine_path).load().artifacts[artifact.id].status == EvolutionStatus.QUARANTINED
    )

    replay_results = {
        "original": _run_candidate_fixture(artifact, "recovery-original", "repeated", True, output_dir / "candidate"),
        "task_family": _run_candidate_fixture(artifact, "recovery-family", "repeated", True, output_dir / "candidate"),
        "global_smoke": _run_candidate_fixture(artifact, "recovery-global", "success", False, output_dir / "candidate"),
        "safety_smoke": _run_candidate_fixture(
            artifact, "recovery-safety", "uncertain", False, output_dir / "candidate"
        ),
    }
    baseline_depth = sum(node.kind == "RecoveryStrategySelected" for node in baseline.trace.nodes)
    replays = [
        _replay_evidence(category, result, baseline_depth=baseline_depth) for category, result in replay_results.items()
    ]
    passed_categories = {item.category for item in replays if item.passed}
    artifact.regression_results = {
        "candidate_cascade_depth": float(
            max(item.cascade_depth for item in replays if item.category != "global_smoke")
        ),
        "unsafe_side_effect_rate": float(sum(item.unsafe_side_effects for item in replays)),
        "blind_retry_rate": float(
            sum("retry" in item.recovery_actions for item in replays if item.category == "safety_smoke")
        ),
        "mandatory_replay_coverage": len(passed_categories & MANDATORY_RECOVERY_REPLAYS)
        / len(MANDATORY_RECOVERY_REPLAYS),
    }
    runtime_recovery_response = payload.response in {kind.value for kind in RecoveryKind}
    if quarantined_before and runtime_recovery_response and MANDATORY_RECOVERY_REPLAYS <= passed_categories:
        decision = registry.accept_if_regression_passes(
            artifact.id,
            rules=[
                RegressionRule("candidate_cascade_depth", MetricDirection.LOWER_IS_BETTER, 1.0),
                RegressionRule("unsafe_side_effect_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
                RegressionRule("blind_retry_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
                RegressionRule("mandatory_replay_coverage", MetricDirection.HIGHER_IS_BETTER, 1.0),
            ],
        )
    else:
        artifact.status = EvolutionStatus.QUARANTINED
        artifact.decision_reason = (
            "response belongs to a non-runtime failure owner"
            if not runtime_recovery_response
            else "mandatory recovery replay did not pass"
        )
        decision = artifact.status

    payload_path = output_dir / "artifacts" / artifact.id / artifact.version / "payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    registry_path = output_dir / "registry.json"
    EvolutionRegistryStore(registry_path).save(registry)
    rollback_path = output_dir / "rollback-proof.json"
    rollback_verified = (
        _prove_recovery_rollback(registry, artifact.id, signature, rollback_path)
        if decision == EvolutionStatus.ACCEPTED
        else True
    )
    report = RecoveryEvolutionReport(
        source_incident=failure.model_dump(mode="json"),
        artifact=artifact,
        replays=replays,
        decision=decision,
        quarantined_before_replay=quarantined_before,
        fresh_candidate_id="fresh-recovery-runtime-v1",
        registry_path=str(registry_path),
        quarantine_registry_path=str(quarantine_path),
        rollback_proof_path=str(rollback_path),
        rollback_verified=rollback_verified,
    )
    _write_report(report, output_dir)
    return report


def _run_candidate_fixture(
    artifact: EvolutionArtifact,
    task_id: str,
    mode: str,
    idempotent: bool,
    artifact_root: Path,
):
    profile = CandidateRuntimeProfile()
    profile.load(artifact, allow_candidate=True)
    return _run_fixture(
        task_id,
        mode=mode,
        idempotent=idempotent,
        artifact_root=artifact_root,
        runtime_profile_digest=f"candidate:{artifact.payload_digest}",
        loaded_profile_artifact_ids=(artifact.id,),
    )


def _run_fixture(
    task_id: str,
    *,
    mode: str,
    idempotent: bool,
    artifact_root: Path,
    runtime_profile_digest: str = "",
    loaded_profile_artifact_ids: tuple[str, ...] = (),
):
    world = RecoveryFixtureWorld()
    return compose_run_coordinator(
        observer=StableRecoveryObserver(world),
        executor=RecoveryFixtureExecutor(mode, world),
        contract_builder=ActionContractMaterializer(
            requirements={
                "dom_button_1": ContractRequirements(
                    verifier_plan=(
                        VerifierSpec(
                            "observation_metadata",
                            "effect_verified",
                            True,
                            criterion_ids=("criterion:recovery-effect-verified",),
                            progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                        ),
                    ),
                    idempotency_key="recovery-fixture:save" if idempotent else "",
                )
            }
        ),
        artifacts=ArtifactStore(artifact_root),
        runtime_profile_digest=runtime_profile_digest,
        loaded_profile_artifact_ids=loaded_profile_artifact_ids,
    ).run_sync(
        RunRequest(
            task_spec=TaskSpec(
                task_id=task_id,
                revision=1,
                objective="exercise recovery cascade",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                requirements=canonical_effect_requirements(
                    ("Save",), OperationClass.REVERSIBLE_WRITE, "recovery-evolution", ()
                ),
                allowed_effect_refs=canonical_effect_requirement_refs(("Save",)),
                success=SuccessExpression(
                    expression_id="success:recovery-effect-verified",
                    operator="criterion",
                    criterion_id="criterion:recovery-effect-verified",
                    requirement_refs=("requirement:effect:1",),
                ),
                evidence_requirements=("receipt evidence",),
                source_request_ref="recovery-evolution",
            )
        )
    )


def _replay_evidence(category: str, result: Any, *, baseline_depth: int) -> RecoveryReplayEvidence:
    actions = [
        str(node.payload.get("decision", {}).get("kind") or "")
        for node in result.trace.nodes
        if node.kind == "RecoveryStrategySelected"
    ]
    depth = len(actions)
    duplicate = int(sum(item == "retry_idempotent" for item in actions) > 1)
    unsafe = int("retry" in actions and category == "safety_smoke")
    if category in {"original", "task_family"}:
        passed = depth <= baseline_depth and result.status == RuntimeStep.ABORTED and duplicate == 0
    elif category == "global_smoke":
        passed = result.status == RuntimeStep.DONE and not actions
    else:
        passed = "retry" not in actions and duplicate == 0
    return RecoveryReplayEvidence(
        category,
        result.run_id,
        result.status.value,
        depth,
        actions,
        int(result.status == RuntimeStep.ABORTED),
        duplicate,
        unsafe,
        passed,
        _trace_path(result),
    )


def _trace_path(result: Any) -> str:
    return next((item.path for item in result.artifacts if item.path.endswith("events.jsonl")), "")


def _prove_recovery_rollback(
    registry: EvolutionRegistry,
    artifact_id: str,
    signature: Any,
    rollback_path: Path,
) -> bool:
    persisted = EvolutionRegistryStore(rollback_path.with_name("accepted-recovery-load-proof.json"))
    persisted.save(registry)
    loaded = persisted.load()
    profile = CandidateRuntimeProfile()
    profile.load(loaded.artifacts[artifact_id])
    contract = ActionContract(
        "rollback-contract",
        "save",
        "save",
        "click",
        "recovery-fixture",
        "recovery-state-v1",
        {"selector": "#save"},
        idempotency_key="recovery-fixture:save",
    )
    context = EvolutionRecoveryContext(failure_signature=signature, task_id="recovery-original")
    patched = profile.recovery_policy().decide(contract, None, context).kind == EvolutionRecoveryAction.ABORT
    profile.rollback(artifact_id)
    restored = profile.recovery_policy().decide(contract, None, context).kind == RecoveryKind.RETRY_IDEMPOTENT

    rolled_back = deepcopy(loaded)
    rolled_back.rollback(artifact_id, reason="M8.3 rollback proof", reviewer="automated-recovery-gate")
    rolled_back_path = rollback_path.with_name("rolled-back-registry.json")
    EvolutionRegistryStore(rolled_back_path).save(rolled_back)
    rejected = False
    try:
        CandidateRuntimeProfile().load(EvolutionRegistryStore(rolled_back_path).load().artifacts[artifact_id])
    except ValueError:
        rejected = True
    proof = {
        "patched_abort": patched,
        "runtime_restored_retry": restored,
        "rolled_back_load_rejected": rejected,
        "rolled_back_registry": str(rolled_back_path),
    }
    rollback_path.write_text(json.dumps(proof, indent=2, sort_keys=True), encoding="utf-8")
    return patched and restored and rejected and rolled_back_path.exists()


def _write_report(report: RecoveryEvolutionReport, output_dir: Path) -> None:
    value = {
        "schema_version": "recovery-cascade-evolution-v1",
        "source_incident": to_json_compatible(report.source_incident),
        "artifact": asdict(report.artifact),
        "replays": [to_json_compatible(item) for item in report.replays],
        "decision": report.decision.value,
        "quarantined_before_replay": report.quarantined_before_replay,
        "fresh_candidate_id": report.fresh_candidate_id,
        "registry_path": report.registry_path,
        "quarantine_registry_path": report.quarantine_registry_path,
        "rollback_proof_path": report.rollback_proof_path,
        "rollback_verified": report.rollback_verified,
    }
    rendered = json.dumps(value, indent=2, sort_keys=True, default=str)
    (output_dir / "recovery-evolution-report.json").write_text(rendered, encoding="utf-8")
    lines = [
        "# Recovery Cascade Evolution Report",
        "",
        f"- Source failure phase: `{report.source_incident.get('phase', '')}`",
        f"- Quarantined before replay: `{str(report.quarantined_before_replay).lower()}`",
        f"- Candidate decision: `{report.decision.value}`",
        f"- Rollback verified: `{str(report.rollback_verified).lower()}`",
        "- Mandatory categories: `original, task_family, global_smoke, safety_smoke`",
        "",
    ]
    (output_dir / "recovery-evolution-report.md").write_text("\n".join(lines), encoding="utf-8")
