"""Executable M8.3 recovery-cascade evolution gate."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.evolution import (
    CandidateRuntimeProfile,
    EvolutionArtifact,
    EvolutionArtifactType,
    EvolutionRegistry,
    EvolutionRegistryStore,
    EvolutionStatus,
    MetricDirection,
    RecoveryPolicyPatchPayload,
    RegressionRule,
)
from affordance_runtime.recovery import BoundedRecoveryPolicy, RecoveryAction, RecoveryContext
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel

MANDATORY_RECOVERY_REPLAYS = {"original", "task_family", "global_smoke", "safety_smoke"}


def _snapshot() -> BrowserSnapshot:
    revision = "recovery-state-v1"
    model = DomAdapter().transduce(
        '<button id="save">Save</button>',
        environment_revision=revision,
        snapshot_id="recovery-snapshot-v1",
        page_revision=revision,
    )
    return BrowserSnapshot(
        Observation(
            revision,
            snapshot_id="recovery-snapshot-v1",
            page_revision=revision,
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
        ),
        model,
    )


class StableRecoveryObserver:
    def capture(self) -> BrowserSnapshot:
        return _snapshot()


@dataclass
class RecoveryFixturePlanner:
    idempotent: bool

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        if state.receipts and state.receipts[-1].success:
            return PlannerDecision(done=True, result={"effect": "verified"})
        contract = ActionContract.from_affordance(
            snapshot.affordance_model.affordances[0],
            intent="exercise bounded recovery",
            backend="recovery-fixture",
            verifier_plan=[VerifierSpec("evidence", "effect_verified", True)],
        )
        return PlannerDecision(
            contract=replace(
                contract,
                idempotency_key="recovery-fixture:save" if self.idempotent else "",
                contract_hash="",
            )
        )


@dataclass
class RecoveryFixtureExecutor:
    mode: str
    backend: str = "recovery-fixture"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        if self.mode == "success":
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


def run_recovery_cascade_evolution(output_dir: Path) -> RecoveryEvolutionReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = _run_fixture(
        "recovery-original",
        mode="repeated",
        idempotent=True,
        recovery=BoundedRecoveryPolicy(),
        artifact_root=output_dir / "baseline",
    )
    incident = baseline.state.recovery_incident
    if incident is None or int(incident.diagnostics()["loop_aborts"]) != 1:
        raise RuntimeError("source run did not produce a real repeated recovery incident")

    signature = incident.root_failure
    payload = RecoveryPolicyPatchPayload(
        schema_version="1.0",
        patch_kind="recovery_policy",
        task_ids=["recovery-original", "recovery-family"],
        signature_match={
            "error_code": signature.error_code,
            "action": signature.action,
            "backend": signature.backend,
            "normalized_error": signature.normalized_error,
        },
        response=RecoveryAction.ABORT.value,
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
        negative_examples=[incident.incident_id],
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
    quarantined_before = EvolutionRegistryStore(quarantine_path).load().artifacts[artifact.id].status == EvolutionStatus.QUARANTINED

    replay_results = {
        "original": _run_candidate_fixture(artifact, "recovery-original", "repeated", True, output_dir / "candidate"),
        "task_family": _run_candidate_fixture(artifact, "recovery-family", "repeated", True, output_dir / "candidate"),
        "global_smoke": _run_candidate_fixture(artifact, "recovery-global", "success", False, output_dir / "candidate"),
        "safety_smoke": _run_candidate_fixture(artifact, "recovery-safety", "uncertain", False, output_dir / "candidate"),
    }
    baseline_depth = int(incident.diagnostics()["cascade_depth"])
    replays = [
        _replay_evidence(category, result, baseline_depth=baseline_depth)
        for category, result in replay_results.items()
    ]
    passed_categories = {item.category for item in replays if item.passed}
    artifact.regression_results = {
        "candidate_cascade_depth": float(max(item.cascade_depth for item in replays if item.category != "global_smoke")),
        "unsafe_side_effect_rate": float(sum(item.unsafe_side_effects for item in replays)),
        "blind_retry_rate": float(
            sum("retry" in item.recovery_actions for item in replays if item.category == "safety_smoke")
        ),
        "mandatory_replay_coverage": len(passed_categories & MANDATORY_RECOVERY_REPLAYS)
        / len(MANDATORY_RECOVERY_REPLAYS),
    }
    if quarantined_before and MANDATORY_RECOVERY_REPLAYS <= passed_categories:
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
        artifact.decision_reason = "mandatory recovery replay did not pass"
        decision = artifact.status

    payload_path = output_dir / "artifacts" / artifact.id / artifact.version / "payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    registry_path = output_dir / "registry.json"
    EvolutionRegistryStore(registry_path).save(registry)
    rollback_path = output_dir / "rollback-proof.json"
    rollback_verified = _prove_recovery_rollback(registry, artifact.id, signature, rollback_path)
    report = RecoveryEvolutionReport(
        source_incident=asdict(incident),
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
    return _run_fixture(task_id, mode=mode, idempotent=idempotent, recovery=profile.recovery_policy(), artifact_root=artifact_root)


def _run_fixture(
    task_id: str,
    *,
    mode: str,
    idempotent: bool,
    recovery: BoundedRecoveryPolicy,
    artifact_root: Path,
):
    return RunCoordinator(
        observer=StableRecoveryObserver(),
        planner=RecoveryFixturePlanner(idempotent),
        executor=RecoveryFixtureExecutor(mode),
        recovery=recovery,
        artifacts=ArtifactStore(artifact_root),
    ).run_sync(TaskEnvelope(task_id, "exercise recovery cascade"))


def _replay_evidence(category: str, result: Any, *, baseline_depth: int) -> RecoveryReplayEvidence:
    diagnostics = result.state.recovery_diagnostics
    incident = result.state.recovery_incident
    actions = [attempt.recovery_action.value for attempt in incident.attempts] if incident else []
    depth = int(diagnostics.get("cascade_depth", 0))
    duplicate = int(diagnostics.get("duplicate_effect_risk_count", 0))
    unsafe = int("retry" in actions and category == "safety_smoke")
    if category in {"original", "task_family"}:
        passed = depth < baseline_depth and actions == [RecoveryAction.ABORT.value]
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
        int(diagnostics.get("loop_aborts", 0)),
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
    context = RecoveryContext(failure_signature=signature, task_id="recovery-original")
    patched = profile.recovery_policy().decide(contract, None, context).action == RecoveryAction.ABORT
    profile.rollback(artifact_id)
    restored = profile.recovery_policy().decide(contract, None, context).action == RecoveryAction.RETRY

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
        "source_incident": report.source_incident,
        "artifact": asdict(report.artifact),
        "replays": [asdict(item) for item in report.replays],
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
        f"- Source cascade depth: `{len(report.source_incident['attempts'])}`",
        f"- Quarantined before replay: `{str(report.quarantined_before_replay).lower()}`",
        f"- Candidate decision: `{report.decision.value}`",
        f"- Rollback verified: `{str(report.rollback_verified).lower()}`",
        "- Mandatory categories: `original, task_family, global_smoke, safety_smoke`",
        "",
    ]
    (output_dir / "recovery-evolution-report.md").write_text("\n".join(lines), encoding="utf-8")
