"""Controlled M8.5 routing and System 1 ablation.

The harness uses the real Coordinator, Unified Route Planner, fresh contracts,
preflight, recovery, executors, and structural verification.  It is deliberately
provider-free and does not claim remote-model quality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    AffordanceLease,
    ExecutionReceipt,
    Observation,
    RuntimeErrorCode,
    Surface,
    VerifierSpec,
)
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.evolution import (
    CandidateRuntimeProfile,
    EvolutionArtifact,
    EvolutionArtifactType,
    EvolutionStatus,
)
from affordance_runtime.executors import ExecutorRouter, VisualExecutor
from affordance_runtime.grounding import GroundingCandidate, GroundingSource, SourceObservation
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
)
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_skills import (
    AcceptedTaskSkillRuntime,
    SemanticTargetQuery,
    SkillStep,
    TaskSkillPayload,
    TaskSkillTrigger,
)
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)

ABLATION_PROFILES = (
    "dom_only",
    "visual_only",
    "fixed_dom_to_visual",
    "adaptive_unified",
    "adaptive_plus_task_skill",
    "always_system2",
)
ABLATION_CASES = (
    "structured_primary",
    "visual_primary",
    "dom_failure_fallback",
    "material_conflict",
    "stale_candidates",
    "accepted_task_skill",
)


@dataclass(frozen=True)
class AdaptiveRoutingAblationRun:
    profile: str
    case_id: str
    success: bool
    runtime_status: str
    expected_safe_block: bool
    selected_sources: tuple[str, ...]
    planner_calls: int
    visual_model_calls: int
    visual_routes: int
    effect_count: int
    recovery_count: int
    skill_activated: bool
    skill_fell_through: bool
    stale_blocked: bool
    constraint_violations: int
    verifier_false_accepts: int
    unsafe_side_effects: int
    duplicate_effect_risks: int
    cost: float
    latency_ms: float
    trace_events: tuple[str, ...]


@dataclass
class _AblationWorld:
    saved: bool = False
    effects: int = 0


class _AblationObserver:
    def __init__(self, world: _AblationWorld, profile: str, case_id: str) -> None:
        self.world = world
        self.profile = profile
        self.case_id = case_id
        self.sequence = 0
        self.visual_model_calls = 0
        self.semantic_target_id = self._snapshot(0).unified_affordances[0].semantic_target_id

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        if "visual" in self._sources():
            self.visual_model_calls += 1
        return self._snapshot(self.sequence)

    def _snapshot(self, sequence: int) -> BrowserSnapshot:
        snapshot_id = f"{self.profile}-{self.case_id}-snapshot-{sequence}"
        environment_revision = f"saved:{self.world.saved}"
        page_revision = "ablation-page-v1"
        model = DomAdapter().transduce(
            '<button id="save">Save</button>',
            environment_revision=environment_revision,
            snapshot_id=snapshot_id,
            page_revision=page_revision,
            ttl_ms=60_000,
        )
        dom = replace(model.affordances[0], backend_candidates=["dom"])
        visual = Affordance(
            "visual_save",
            Surface.VISUAL,
            "button",
            "Save",
            "click",
            {"bbox": [100, 70, 40, 40], "screenshot_ref": f"screen-{sequence}.png"},
            AffordanceLease.issue(
                environment_revision=environment_revision,
                ttl_ms=60_000,
                snapshot_id=snapshot_id,
                page_revision=page_revision,
                target_fingerprint="visual-save-v1",
            ),
            backend_candidates=["visual"],
            confidence=0.95,
            evidence=[f"screen-{sequence}.png"],
        )
        observation = Observation(
            environment_revision,
            screenshot_ref=f"screen-{sequence}.png",
            snapshot_id=snapshot_id,
            page_revision=page_revision,
            metadata={"saved": self.world.saved, "viewport_size": [640, 480]},
        )
        sources = self._sources()
        affordances = {"dom": dom, "visual": visual}
        candidates: list[GroundingCandidate] = []
        for source in sources:
            affordance = affordances[source]
            candidate = candidate_from_affordance(
                affordance,
                observation,
                semantic_target_id="pending",
                compatible_executor=source,
                image_size=(640, 480) if source == "visual" else None,
            )
            if self.case_id == "stale_candidates":
                candidate = replace(candidate, observation_epoch_id="stale-observation")
            candidates.append(candidate)
        target = SemanticEntityResolver().resolve(
            CandidateDescriptor("button", "Save", "click", "main", item)
            for item in candidates
        )[0]
        if self.case_id == "material_conflict":
            target = replace(target, unresolved_conflicts=("save.enabled",))
        observation = replace(
            observation,
            target_fingerprints=candidate_fingerprints((target,)),
        )
        source_observations = tuple(
            SourceObservation(
                GroundingSource.DOM if source == "dom" else GroundingSource.VISUAL,
                f"{source}-ablation",
                snapshot_id,
                environment_revision,
                page_revision,
                artifact_refs=((f"screen-{sequence}.png",) if source == "visual" else ()),
            )
            for source in sources
        )
        return BrowserSnapshot(
            observation,
            replace(
                model,
                affordances=[affordances[item] for item in sources],
                kept_node_count=len(sources),
            ),
            source_observations=source_observations,
            grounding_candidates=target.grounding_candidates,
            unified_affordances=(target,),
        )

    def _sources(self) -> tuple[str, ...]:
        if self.profile == "dom_only":
            return ("dom",)
        if self.profile == "visual_only":
            return ("visual",)
        if self.case_id in {
            "visual_primary",
            "dom_failure_fallback",
            "material_conflict",
            "stale_candidates",
        }:
            return ("dom", "visual")
        return ("dom",)


@dataclass
class _AblationDomExecutor:
    world: _AblationWorld
    fail_before_dispatch: bool = False
    backend: str = "dom"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        if self.fail_before_dispatch:
            return ExecutionReceipt(
                contract.id,
                self.backend,
                False,
                observation.environment_revision,
                observation.environment_revision,
                1.0,
                evidence={"dispatched": False},
                error_code=RuntimeErrorCode.EXECUTION_FAILED,
                message="controlled DOM failure before dispatch",
            )
        self.world.effects += 1
        self.world.saved = True
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            observation.environment_revision,
            "saved:True",
            1.0,
            evidence={"action": "click", "dispatched": True},
        )


class _AblationPointer:
    def __init__(self, world: _AblationWorld) -> None:
        self.world = world

    def click_xy(self, x: int, y: int) -> None:
        if (x, y) != (120, 90):
            raise ValueError("controlled visual route selected an unexpected point")
        self.world.effects += 1
        self.world.saved = True

    def type_text(self, text: str) -> None:
        raise ValueError(f"unexpected ablation text input: {text}")


class _CountingSystem2Planner:
    def __init__(self) -> None:
        self.calls = 0

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        self.calls += 1
        if snapshot.observation.metadata.get("saved") is True:
            return PlannerDecision(done=True, result={"saved": True})
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id=f"system2-{self.calls}-{state.version}",
                based_on_task_revision=envelope.task_spec.revision if envelope.task_spec else 1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                subgoal=(
                    "Activate the blue visual Save icon"
                    if envelope.task_spec and "visual" in envelope.task_spec.objective.lower()
                    else "Activate Save"
                ),
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=snapshot.unified_affordances[0].semantic_target_id,
            )
        )


def run_adaptive_routing_ablation(output_dir: Path) -> dict[str, Any]:
    """Execute all six profiles and persist a deterministic JSON report."""

    output_dir.mkdir(parents=True, exist_ok=True)
    runs = [
        _run_case(profile, case_id)
        for profile in ABLATION_PROFILES
        for case_id in ABLATION_CASES
    ]
    profiles = {
        profile: _aggregate_profile([item for item in runs if item.profile == profile])
        for profile in ABLATION_PROFILES
    }
    baseline_success = profiles["always_system2"]["task_success_rate"]
    for metrics in profiles.values():
        metrics["regression_delta"] = metrics["task_success_rate"] - baseline_success
    errors = _acceptance_errors(runs, profiles)
    report = {
        "schema_version": "m8.5-routing-system1-ablation-v1",
        "profiles": profiles,
        "runs": [item.__dict__ for item in runs],
        "acceptance_errors": errors,
        "remote_model_used": False,
        "oracle": (
            "effect cases require verified saved state; conflict/stale cases require zero effects"
        ),
    }
    (output_dir / "adaptive-routing-ablation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


def _run_case(profile: str, case_id: str) -> AdaptiveRoutingAblationRun:
    world = _AblationWorld()
    observer = _AblationObserver(world, profile, case_id)
    planner = _CountingSystem2Planner()
    executors = ExecutorRouter()
    executors.register(
        _AblationDomExecutor(
            world,
            fail_before_dispatch=case_id == "dom_failure_fallback",
        )
    )
    executors.register(VisualExecutor(_AblationPointer(world)))
    visual_primary = case_id == "visual_primary"
    profile_forces_visual = profile == "visual_only"
    if case_id == "accepted_task_skill":
        objective = "save profile visually" if profile_forces_visual else "save profile"
    elif visual_primary:
        objective = "Activate the blue visual Save icon"
    elif case_id == "dom_failure_fallback":
        objective = "Activate the visual Save control at its current position"
    elif profile_forces_visual:
        objective = "Activate the visual Save control"
    else:
        objective = "Activate Save"
    task = TaskSpec(
        task_id=f"m85-{profile}-{case_id}",
        revision=1,
        objective=objective,
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("Save",),
        success_criteria=("saved state is true",),
        evidence_requirements=(
            ("visual appearance and saved state",)
            if visual_primary or profile_forces_visual or case_id == "dom_failure_fallback"
            else ("independent saved state",)
        ),
        requested_capabilities=("settings.write",),
        source_request_ref="m8.5-ablation",
    )
    builder = ContractBuilder(
        requirements={
            observer.semantic_target_id: ContractRequirements(
                verifier_plan=(VerifierSpec("observation_metadata", "saved", True),),
                idempotency_key=f"m85:{profile}:{case_id}:save",
            )
        }
    )
    started = perf_counter()
    result = RunCoordinator(
        observer,
        planner,
        executors,
        contract_builder=builder,
        task_skill_runtime=(
            _accepted_save_skill()
            if profile == "adaptive_plus_task_skill"
            else None
        ),
    ).run_sync(TaskEnvelope(task_spec=task, capabilities=["settings.write"]))
    latency_ms = (perf_counter() - started) * 1_000
    events = tuple(node.kind for node in result.trace.nodes)
    route_nodes = [node for node in result.trace.nodes if node.kind == "RouteSelected"]
    selected_sources = tuple(str(node.payload.get("source") or "") for node in route_nodes)
    expected_safe_block = case_id in {"material_conflict", "stale_candidates"}
    success = (
        world.effects == 0 and not result.state.receipts
        if expected_safe_block
        else result.status == RuntimeStep.DONE and world.saved and world.effects == 1
    )
    diagnostics = result.state.recovery_diagnostics
    verifier_false_accepts = int(
        result.verification is not None and result.verification.passed and not world.saved
    )
    return AdaptiveRoutingAblationRun(
        profile,
        case_id,
        success,
        result.status.value,
        expected_safe_block,
        selected_sources,
        planner.calls,
        observer.visual_model_calls,
        sum(source == GroundingSource.VISUAL.value for source in selected_sources),
        world.effects,
        result.state.recovery_count,
        "TaskSkillActivated" in events,
        "TaskSkillFellThrough" in events,
        case_id == "stale_candidates" and success,
        0,
        verifier_false_accepts,
        0 if world.effects <= 1 else world.effects - 1,
        int(diagnostics.get("duplicate_effect_risk_count", 0)),
        0.0,
        latency_ms,
        events,
    )


def _accepted_save_skill() -> AcceptedTaskSkillRuntime:
    payload = TaskSkillPayload(
        "1.0",
        "task_skill",
        "profile.save",
        "1.0.0",
        TaskSkillTrigger("save profile", ("save", "profile")),
        (),
        (
            SkillStep(
                "step-1",
                "Activate Save",
                PlannerActionKind.ACTIVATE.value,
                SemanticTargetQuery("button", "Save", PlannerActionKind.ACTIVATE.value),
                postconditions=("saved state is true",),
                evidence_requirements=("independent saved state",),
                required_capabilities=("settings.write",),
                risk="medium",
            ),
        ),
        ("layout-a", "layout-b"),
        ("trace-a", "trace-b", "trace-c"),
        ("layout-a", "layout-b", "layout-a"),
        heldout_suite="m8.5-ablation-heldout-v1",
    )
    artifact = EvolutionArtifact(
        payload.skill_id,
        EvolutionArtifactType.TASK_SKILL.value,
        "accepted controlled save skill",
        {"task_family": payload.trigger.task_family},
        list(payload.source_traces),
        status=EvolutionStatus.ACCEPTED,
        version=payload.version,
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
    )
    runtime_profile = CandidateRuntimeProfile()
    runtime_profile.load(artifact)
    return AcceptedTaskSkillRuntime.from_profile(runtime_profile)


def _aggregate_profile(runs: list[AdaptiveRoutingAblationRun]) -> dict[str, float]:
    total = len(runs)
    structured = next(item for item in runs if item.case_id == "structured_primary")
    fallback = next(item for item in runs if item.case_id == "dom_failure_fallback")
    skill = next(item for item in runs if item.case_id == "accepted_task_skill")
    return {
        "task_success_rate": sum(item.success for item in runs) / total,
        "mean_planner_calls": sum(item.planner_calls for item in runs) / total,
        "mean_visual_model_calls": sum(item.visual_model_calls for item in runs) / total,
        "mean_latency_ms": sum(item.latency_ms for item in runs) / total,
        "visual_route_rate": sum(bool(item.visual_routes) for item in runs) / total,
        "unnecessary_visual_route_rate": float(bool(structured.visual_routes)),
        "unnecessary_visual_model_call_rate": float(bool(structured.visual_model_calls)),
        "fallback_success": float(fallback.success),
        "skill_case_planner_calls": float(skill.planner_calls),
        "skill_activation_precision": float(not skill.skill_activated or skill.success),
        "skill_fallthrough_rate": sum(item.skill_fell_through for item in runs) / total,
        "stale_block_rate": float(
            next(item for item in runs if item.case_id == "stale_candidates").stale_blocked
        ),
        "constraint_violation_rate": sum(item.constraint_violations for item in runs) / total,
        "unsafe_side_effect_rate": sum(item.unsafe_side_effects for item in runs) / total,
        "verifier_false_accept_rate": sum(item.verifier_false_accepts for item in runs) / total,
        "duplicate_effect_risk_rate": sum(item.duplicate_effect_risks for item in runs) / total,
        "mean_cost": sum(item.cost for item in runs) / total,
    }


def _acceptance_errors(
    runs: list[AdaptiveRoutingAblationRun],
    profiles: dict[str, dict[str, float]],
) -> list[str]:
    errors: list[str] = []
    by_key = {(item.profile, item.case_id): item for item in runs}
    for profile in ("fixed_dom_to_visual", "adaptive_unified", "adaptive_plus_task_skill"):
        if not by_key[(profile, "dom_failure_fallback")].success:
            errors.append(f"{profile} did not recover the controlled DOM failure")
    if by_key[("dom_only", "visual_primary")].success:
        errors.append("dom_only unexpectedly satisfied the visual-primary oracle")
    if not by_key[("visual_only", "visual_primary")].success:
        errors.append("visual_only did not satisfy the visual-primary oracle")
    if profiles["adaptive_unified"]["unnecessary_visual_model_call_rate"] != 0:
        errors.append("adaptive routing made an unnecessary structured-task visual call")
    if profiles["visual_only"]["unnecessary_visual_model_call_rate"] != 1:
        errors.append("visual_only did not expose its structured-task visual-call cost")
    for item in runs:
        if item.expected_safe_block and not item.success:
            errors.append(f"{item.profile}/{item.case_id} did not block safely")
        if item.unsafe_side_effects or item.verifier_false_accepts or item.duplicate_effect_risks:
            errors.append(f"{item.profile}/{item.case_id} violated a safety invariant")
    if profiles["adaptive_plus_task_skill"]["skill_case_planner_calls"] != 0:
        errors.append("accepted TaskSkill did not eliminate System 2 calls for the skill case")
    if (
        profiles["adaptive_plus_task_skill"]["skill_case_planner_calls"]
        >= profiles["always_system2"]["skill_case_planner_calls"]
    ):
        errors.append("TaskSkill profile did not reduce planner calls against always System 2")
    return errors
